// Pure, transport-agnostic genesis-transaction builder for the GoalShow
// covenant — the performer-side "create goal show" flow. One transaction
// that is simultaneously the token genesis AND the pot seed: the minting
// NFT is created directly into the covenant (category = input-0 parent's
// txid). A split mint-then-seed flow leaves a window to mint forged
// receipts; never do it (docs/covenant-goal-shows.md).
//
// No network calls: the ElectrumNetworkProvider is a dummy for address
// validation only (every input's source output is supplied), and the
// WizardConnect request object is returned for the caller to transport.
// The wallet signs the performer's P2PKH parent input (inputPaths
// [[0, 'receive', 0]]); there is no covenant input at genesis.
import { Contract, ElectrumNetworkProvider, TransactionBuilder, placeholderP2PKHUnlocker } from 'cashscript';
import { hexToBin } from '@bitauth/libauth';
import { decodeAddr, mapUtxo, toRelaySourceOutput } from './pledge_tx.mjs';

export const POT_SEED = 800n; // token-output dust floor is ~678; keep margin.
// Recoverable via a successful claim; locked as dust on an unmet show.
export const MIN_GOAL_SATS = 100_000n; // mirrors lovecash.config.MIN_GOAL_SATS
const CHANGE_DUST = 546n;
const FEE_CEILING = 1000n; // selection pass only; the real fee is measured
// A placeholder unlocker leaves the funder's unlocking bytecode EMPTY; the
// wallet fills it with a schnorr sig push (66) + pubkey push (34).
const SIGNED_P2PKH_SCRIPTSIG = 100n;

/**
 * Build the one-tx genesis+seed for a new goal show.
 *
 * @param {object} o
 * @param {object} o.artifact - compiled goal_show.json artifact
 * @param {bigint|number} o.goalSats - covenant goal (>= MIN_GOAL_SATS)
 * @param {bigint|number} o.deadline - covenant deadline (block height, >= 1)
 * @param {Array}  o.funderUtxos - API-shaped UTXOs of the performer address
 * @param {string} o.funderAddress - performer cashaddr (P2PKH; token-aware ok)
 * @param {bigint|number} [o.seedSats=POT_SEED]
 * @param {object} [o.provider] - testing only: real provider instead of the dummy
 * @param {object} [o.funderUnlocker] - testing only: real unlocker instead of placeholder
 * @returns {Promise<{request: object, category: string, potAddress: string,
 *   potTokenAddress: string, seedSats: bigint, changeSats: bigint,
 *   feeSats: bigint, builder: TransactionBuilder}>}
 *   request is ready for `DappConnectionManager.signTransaction(request)`.
 *   category is DISPLAY hex (what Electrum/wallets show).
 */
export async function buildDeployTx({
  artifact,
  goalSats,
  deadline,
  funderUtxos,
  funderAddress,
  seedSats = POT_SEED,
  provider = null,
  funderUnlocker = null,
  userPrompt = 'Create goal show',
}) {
  const goal = BigInt(goalSats);
  const seed = BigInt(seedSats);
  if (goal < MIN_GOAL_SATS) throw new Error(`goal below the minimum (${MIN_GOAL_SATS} sats)`);
  if (!Number.isSafeInteger(Number(deadline)) || BigInt(deadline) < 1n) {
    throw new Error('deadline must be a block height >= 1');
  }
  if (seed < 678n) throw new Error('seed below the token-output dust floor (678 sats)');

  const funder = decodeAddr(funderAddress);
  const performerPkh = funder.payload;

  // The genesis parent MUST be input 0 spending output index 0 (CHIP-2022-02:
  // only "token genesis inputs" — outpoint index 0 — can create a category).
  // Exactly one funding input: smallest vout-0 tokenless UTXO covering the
  // worst-case total. The real fee is measured after the first build.
  const need = seed + FEE_CEILING + CHANGE_DUST;
  const parent = funderUtxos
    .filter((u) => !u.token && u.tx_pos === 0 && BigInt(u.value) >= need)
    .sort((a, b) => Number(BigInt(a.value) - BigInt(b.value)))[0];
  if (!parent) {
    throw new Error(
      `genesis needs a tokenless UTXO at output index 0 covering ${need} sats — ` +
      'send coins to your own address in your wallet (self-send), then retry'
    );
  }
  const category = parent.tx_hash; // display hex, as Electrum reports it

  const net =
    provider ??
    new ElectrumNetworkProvider(funder.prefix === 'bchtest' ? 'chipnet' : 'mainnet');
  const contract = new Contract(
    artifact,
    [performerPkh, goal, BigInt(deadline), hexToBin(category).reverse()],
    { provider: net },
  );

  const parentUtxo = mapUtxo(parent);
  const unlocker = funderUnlocker ?? placeholderP2PKHUnlocker(funderAddress);
  const minting = { category, amount: 0n, nft: { capability: 'minting', commitment: '' } };

  const assemble = (fee) =>
    new TransactionBuilder({ provider: net })
      .addInput(parentUtxo, unlocker)
      .addOutput({ to: funderAddress, amount: parentUtxo.satoshis - seed - fee }) // vout 0: change
      .addOutput({ to: contract.tokenAddress, amount: seed, token: minting }); // vout 1: the pot

  // Exact fee at 1 sat/byte: tx size is amount-independent, and the
  // wallet adds SIGNED_P2PKH_SCRIPTSIG bytes over the placeholder build.
  // (The dry run must carry the ceiling: cashscript refuses fee/byte < 1.)
  const unsignedBytes = BigInt(assemble(FEE_CEILING).build().length / 2);
  const fee = unsignedBytes + SIGNED_P2PKH_SCRIPTSIG;
  if (fee > FEE_CEILING) throw new Error(`genesis fee ${fee} exceeds sanity ceiling`);
  const change = parentUtxo.satoshis - seed - fee;
  if (change < CHANGE_DUST) {
    throw new Error(`change would be dust (${change} sats) — pick a larger funding UTXO`);
  }
  const builder = assemble(fee);

  // broadcast:false — the wallet signs and hands the tx BACK to us; the
  // relay broadcasts (POST /api/broadcast), which sanity-checks the token
  // category first and keeps the bytes when a wallet mangles them. A
  // wallet-side broadcast also races the relay's genesis registration.
  const wc = builder.generateWcTransactionObject({ broadcast: false, userPrompt });
  return {
    request: {
      transaction: {
        transaction: builder.build(),
        sourceOutputs: wc.sourceOutputs.map(toRelaySourceOutput),
        broadcast: false,
        userPrompt,
      },
      inputPaths: [[0, 'receive', 0]], // the parent input — MUST be input 0
    },
    category,
    potAddress: contract.address,
    potTokenAddress: contract.tokenAddress,
    seedSats: seed,
    changeSats: change,
    feeSats: fee,
    builder, // for tests (mock evaluation) and advanced transports
  };
}
