// Pure, transport-agnostic pledge-transaction builder for the GoalShow
// covenant. No network calls: the ElectrumNetworkProvider is a dummy for
// address validation only (every input's source output is supplied), and
// the WizardConnect request object is returned for the caller to transport.
import { Contract, ElectrumNetworkProvider, TransactionBuilder, placeholderP2PKHUnlocker } from 'cashscript';
import { decodeCashAddress, encodeCashAddress, CashAddressType, hexToBin, binToHex } from '@bitauth/libauth';

const RECEIPT_DUST = 800n; // token-output dust incl. 28-byte commitment
const CHANGE_DUST = 546n;

const le64 = (n) => { const b = Buffer.alloc(8); b.writeBigUInt64LE(n); return new Uint8Array(b); };

// Mirror of @wizardconnect/core's sourceOutputToRelay (present in
// dist/protocols/hdwalletv1-serialize.js but NOT exported from the package).
// The relay transport is a bare JSON.stringify — no replacer — so every
// value must be plain JSON: hex strings + `<bigint: Xn>` tags. Token
// category/commitment stay in libauth-native byte order (the wallet parses
// them back with the same helpers).
function toRelaySourceOutput(so) {
  const r = {
    outpointTransactionHash: binToHex(so.outpointTransactionHash),
    outpointIndex: so.outpointIndex,
    unlockingBytecode: binToHex(so.unlockingBytecode),
    sequenceNumber: so.sequenceNumber,
    valueSatoshis: `<bigint: ${so.valueSatoshis}n>`,
    lockingBytecode: binToHex(so.lockingBytecode),
  };
  if (so.token) {
    r.token = {
      category: binToHex(so.token.category),
      amount: `<bigint: ${so.token.amount}n>`,
      ...(so.token.nft && {
        nft: {
          ...(so.token.nft.capability !== undefined && { capability: so.token.nft.capability }),
          ...(so.token.nft.commitment !== undefined && { commitment: binToHex(so.token.nft.commitment) }),
        },
      }),
    };
  }
  return r;
}

// libauth decodeCashAddress returns an error STRING on failure.
export function decodeAnyAddr(address) {
  const d = decodeCashAddress(address);
  if (typeof d === 'string') throw new Error(`invalid cashaddr: ${d}`);
  return d; // { payload, prefix, type }
}

export function decodeAddr(address) {
  const d = decodeAnyAddr(address);
  if (!d.payload || d.payload.length !== 20) throw new Error('pledge needs a 20-byte (P2PKH) address');
  return d;
}

export function toTokenAddress(address) {
  const d = decodeAddr(address);
  const r = encodeCashAddress({ prefix: d.prefix, type: CashAddressType.p2pkhWithTokens, payload: d.payload });
  return typeof r === 'string' ? r : r.address;
}

// API wire shape -> cashscript Utxo. Category stays DISPLAY hex here: the
// SDK feeds it straight to libauth, which owns the display/raw reversal.
const mapUtxo = (u) => ({
  txid: u.tx_hash,
  vout: u.tx_pos,
  satoshis: BigInt(u.value),
  token: u.token
    ? { category: u.token.category, amount: BigInt(u.token.amount ?? 0), nft: u.token.nft }
    : undefined,
});

/**
 * Build a GoalShow pledge transaction for wallet signing.
 *
 * @param {object} o
 * @param {object} o.artifact - compiled goal_show.json artifact
 * @param {object} o.contractParams - { performerPkh (hex), goalSats, deadline, categoryDisplayHex }
 * @param {object} o.potUtxo - API-shaped pot UTXO (must carry the minting NFT)
 * @param {Array}  o.funderUtxos - API-shaped UTXOs of the funder address
 * @param {string} o.funderAddress - viewer cashaddr (P2PKH; token-aware ok)
 * @param {bigint|number} o.amountSats - pledge amount (>= 546)
 * @param {bigint|number} [o.feeSats=1000]
 * @param {object} [o.provider] - testing only: real provider instead of the dummy
 * @param {object} [o.funderUnlocker] - testing only: real unlocker instead of placeholder
 * @returns {Promise<{request: {transaction: object, inputPaths: Array}, changeSats: bigint, fundingInputIndices: number[], builder: TransactionBuilder}>}
 *   request is ready for `DappConnectionManager.signTransaction(request)`.
 *   inputPaths covers ONLY the funder P2PKH input(s) — the pot input is
 *   complete (covenant needs no signature), so it is left out.
 */
export async function buildPledgeTx({
  artifact,
  contractParams: { performerPkh, goalSats, deadline, categoryDisplayHex },
  potUtxo,
  funderUtxos,
  funderAddress,
  amountSats,
  feeSats = 1000n,
  provider = null,
  funderUnlocker = null,
  userPrompt = 'Pledge to goal show',
}) {
  const amount = BigInt(amountSats);
  const fee = BigInt(feeSats);
  if (amount < 546n) throw new Error('pledge below dust (min 546 sats)');
  if (!Number.isSafeInteger(Number(deadline)) || BigInt(deadline) < 1n) {
    throw new Error('deadline must be >= 1 (pledge txs carry locktime 0)');
  }

  const funder = decodeAddr(funderAddress);
  const pledgerPkh = funder.payload;

  // Pot must carry the minting NFT of this show's category.
  if (potUtxo?.token?.nft?.capability !== 'minting') throw new Error('pot UTXO has no minting NFT');
  if (potUtxo.token.category !== categoryDisplayHex) throw new Error('pot NFT category mismatch');

  // The covenant admits exactly one funding input (tx.inputs.length == 2):
  // pick the smallest single tokenless UTXO that covers everything.
  const need = amount + RECEIPT_DUST + fee + CHANGE_DUST;
  const funding = funderUtxos
    .filter((u) => !u.token && BigInt(u.value) >= need)
    .sort((a, b) => Number(BigInt(a.value) - BigInt(b.value)))[0];
  if (!funding) {
    throw new Error(`no single UTXO covers pledge+dust+fee (${need} sats) — consolidate in your wallet first`);
  }

  // Provider is a dummy: never network-called, all source outputs supplied.
  const net = provider ?? new ElectrumNetworkProvider('mainnet');
  const contract = new Contract(
    artifact,
    [hexToBin(performerPkh), BigInt(goalSats), BigInt(deadline), hexToBin(categoryDisplayHex).reverse()],
    { provider: net },
  );

  const pot = mapUtxo(potUtxo);
  const fund = mapUtxo(funding);
  const change = fund.satoshis - amount - RECEIPT_DUST - fee; // >= 546 by `need`
  const minting = { category: categoryDisplayHex, amount: 0n, nft: { capability: 'minting', commitment: potUtxo.token.nft.commitment ?? '' } };
  const receipt = { category: categoryDisplayHex, amount: 0n, nft: { capability: 'none', commitment: binToHex(Uint8Array.from([...pledgerPkh, ...le64(amount)])) } };

  const builder = new TransactionBuilder({ provider: net })
    .addInput(pot, contract.unlock.pledge(pledgerPkh))
    .addInput(fund, funderUnlocker ?? placeholderP2PKHUnlocker(funderAddress))
    .addOutput({ to: contract.tokenAddress, amount: pot.satoshis + amount, token: minting })
    .addOutput({ to: toTokenAddress(funderAddress), amount: RECEIPT_DUST, token: receipt })
    .addOutput({ to: funderAddress, amount: change })
    .setLocktime(0); // passes locktime < deadline for any deadline >= 1

  // WizardConnect hdwalletv1 request shape (reconciled against installed
  // @wizardconnect/core 0.2.4 — NOT the lagging docs):
  //  - transaction.transaction: HEX (the relay does bare JSON.stringify;
  //    libauth objects carry bigint/Uint8Array and would not survive).
  //    Funder unlocking bytecode stays empty (placeholder) — the wallet
  //    fills it per inputPaths.
  //  - sourceOutputs: relay-safe JSON via toRelaySourceOutput.
  //  - the pot input (index 0) is complete as-is and absent from inputPaths.
  const wc = builder.generateWcTransactionObject({ broadcast: true, userPrompt });
  return {
    request: {
      transaction: {
        transaction: builder.build(),
        sourceOutputs: wc.sourceOutputs.map(toRelaySourceOutput),
        broadcast: true,
        userPrompt,
      },
      inputPaths: [[1, 'receive', 0]], // [inputIndex, pathName, addressIndex]
    },
    changeSats: change,
    fundingInputIndices: [1],
    builder, // for tests (mock evaluation) and advanced transports
  };
}
