"""The sandbox chain: Solidity contracts run on an in-memory EVM. Nothing here is a real network.

artifacts.py   the compiled contracts (built by contracts/build.mjs, committed)
codec.py       ABI encoding and decoding, revert reasons and event logs
evm.py         SandboxChain: deploy contracts, send transactions, read state
"""
