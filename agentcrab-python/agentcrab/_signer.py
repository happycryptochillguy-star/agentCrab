"""Signing utilities: EIP-712 typed data, raw transactions, Safe tx hashes."""

from eth_account import Account
from eth_account.messages import encode_defunct
from hexbytes import HexBytes


def sign_typed_data(private_key: str, typed_data: dict) -> str:
    """Sign EIP-712 typed data and return 0x-prefixed hex signature.

    Used for: Safe deploy (CreateProxy), CLOB auth, order placement.
    """
    sig = Account.sign_typed_data(
        private_key,
        typed_data["domain"],
        typed_data["types"],
        typed_data["message"],
    )
    return "0x" + sig.signature.hex()


def sign_transaction(private_key: str, tx: dict) -> str:
    """Sign a raw transaction and return 0x-prefixed hex of the signed bytes.

    Used for: BSC deposits, Polygon approve txs.
    """
    signed = Account.sign_transaction(tx, private_key)
    return "0x" + signed.raw_transaction.hex()


def sign_safe_tx_hash(private_key: str, hash_hex: str) -> str:
    """Personal-sign a SafeTx hash (bytes32) and return 0x-prefixed hex signature.

    Used for: Safe token approvals via relayer.
    """
    account = Account.from_key(private_key)
    sig = account.sign_message(encode_defunct(HexBytes(hash_hex)))
    return "0x" + sig.signature.hex()
