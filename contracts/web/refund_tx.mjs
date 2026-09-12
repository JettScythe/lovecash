// Pure, transport-agnostic refund-transaction builder for the GoalShow
// covenant. refund() takes no covenant arguments (the receipt's own P2PKH
// input proves ownership and the payout is locked to the committed pkh),
// so ONLY input 1 — the receipt — needs the wallet's signature.
import { Contract, ElectrumNetworkProvider, TransactionBuilder, placeholderP2PKHUnlocker } from 'cashscript';
import { hexToBin, binToHex } from '@bitauth/libauth';
import { decodeAddr, mapUtxo, toRelaySourceOutput } from './pledge_tx.mjs';

const RECEIPT_DUST = 800n;

// 8-byte little-endian -> bigint, browser-safe.
function fromLe64(bytes) {
  let v = 0n;
  for (let i = 7; i >= 0; i--) v = (v << 8n) | BigInt(bytes[i]);
  return v;
}

/** Decode + validate a receipt NFT's 28-byte commitment. Returns {pkhHex, amount}. */
export function parseReceiptCommitment(commitmentHex) {
  const bytes = hexToBin(commitmentHex);
  if (bytes.length !== 28) throw new Error('receipt commitment must be 28 bytes');
  return { pkhHex: binToHex(bytes.slice(0, 20)), amount: fromLe64(bytes.slice(20)) };
}

/**
 * Build a GoalShow refund transaction for wallet signing.
 *
 * @param {object} o
 * @param {object} o.artifact - compiled goal_show.json artifact
 * @param {object} o.contractParams - { performerPkh, goalSats, deadline, categoryDisplayHex }
 * @param {object} o.potUtxo - API-shaped pot UTXO (must carry the minting NFT)
 * @param {object} o.receiptUtxo - API-shaped receipt-NFT UTXO (immutable, same category)
 * @param {string} o.funderAddress - viewer cashaddr (must match the receipt's committed pkh)
 * @param {bigint|number} o.deadline - refund locktime (height-based CLTV lower bound)
 * @param {bigint|number} [o.feeSats=1000] - shrunk automatically near the dust floor
 * @param {object} [o.provider] - testing only
 * @param {object} [o.funderUnlocker] - testing only: real unlocker for the receipt input
 */
export async function buildRefundTx({
  artifact,
  contractParams: { performerPkh, goalSats, deadline: contractDeadline, categoryDisplayHex },
  potUtxo,
  receiptUtxo,
  funderAddress,
  deadline,
  feeSats = 1000n,
  provider = null,
  funderUnlocker = null,
  userPrompt = 'Refund goal-show pledge',
}) {
  deadline = BigInt(deadline);
  if (deadline < 1n) throw new Error('deadline must be >= 1');

  const funder = decodeAddr(funderAddress);
  const pledgerPkh = funder.payload;

  if (potUtxo?.token?.nft?.capability !== 'minting') throw new Error('pot UTXO has no minting NFT');
  if (potUtxo.token.category !== categoryDisplayHex) throw new Error('pot NFT category mismatch');

  // Receipt: immutable NFT of this show's category, committed to THIS pkh.
  if (receiptUtxo?.token?.nft?.capability !== 'none') throw new Error('receipt is not an immutable NFT');
  if (receiptUtxo.token.category !== categoryDisplayHex) throw new Error('receipt category mismatch');
  const { pkhHex, amount } = parseReceiptCommitment(receiptUtxo.token.nft.commitment);
  if (pkhHex !== binToHex(pledgerPkh)) throw new Error('receipt is committed to a different address');
  if (amount < 546n) throw new Error('receipt amount below dust');
  if (amount > BigInt(potUtxo.value)) throw new Error('receipt amount exceeds pot value');

  // Fold the receipt's dust into the payout: pot -= amount (exact), payout =
  // amount + dust - fee. Near the dust floor the fee shrinks so the payout
  // stays >= 546 (amount 546 -> payout 546, fee 800).
  const maxFee = amount + RECEIPT_DUST - 546n;
  const fee = BigInt(feeSats) <= maxFee ? BigInt(feeSats) : maxFee;
  const payout = amount + RECEIPT_DUST - fee;

  // Dummy provider: never network-called, but its network must match the
  // address prefixes or the builder rejects bchtest outputs.
  const net =
    provider ??
    new ElectrumNetworkProvider(funder.prefix === 'bchtest' ? 'chipnet' : 'mainnet');
  const contract = new Contract(
    artifact,
    [hexToBin(performerPkh), BigInt(goalSats), BigInt(contractDeadline), hexToBin(categoryDisplayHex).reverse()],
    { provider: net },
  );

  const pot = mapUtxo(potUtxo);
  const receipt = mapUtxo(receiptUtxo);
  const minting = { category: categoryDisplayHex, amount: 0n, nft: { capability: 'minting', commitment: potUtxo.token.nft.commitment ?? '' } };

  const builder = new TransactionBuilder({ provider: net })
    .addInput(pot, contract.unlock.refund())
    .addInput(receipt, funderUnlocker ?? placeholderP2PKHUnlocker(funderAddress))
    .addOutput({ to: contract.tokenAddress, amount: pot.satoshis - amount, token: minting })
    .addOutput({ to: funderAddress, amount: payout })
    .setLocktime(Number(deadline)); // tx.time >= deadline (height CLTV)

  const wc = builder.generateWcTransactionObject({ broadcast: true, userPrompt });
  return {
    request: {
      transaction: {
        transaction: builder.build(),
        sourceOutputs: wc.sourceOutputs.map(toRelaySourceOutput),
        broadcast: true,
        userPrompt,
      },
      // Only input 1 (the receipt's P2PKH) needs the wallet's key; the
      // covenant input carries no placeholders since refund() is argless.
      inputPaths: [[1, 'receive', 0]],
    },
    payoutSats: payout,
    feeSats: fee,
    fundingInputIndices: [0, 1],
    builder, // for tests (mock evaluation) and advanced transports
  };
}
