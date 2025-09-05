// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title MetadataRegistry
/// @notice 메타데이터 레코드 생성/수정 내역을 온체인에 기록
///         - recordId: 레코드 식별자(임의의 bytes32)
///         - contentHash: 오프체인 JSON 등의 SHA-256(32바이트) 권장
///         - uri: 오프체인 위치(IPFS/HTTP 등)
contract MetadataRegistry {
    struct Item {
        bytes32 contentHash;
        string uri;
        uint256 version;
        address owner;
        uint256 createdAt;
        uint256 updatedAt;
        address updatedBy;
    }

    mapping(bytes32 => Item) public items; // recordId => Item

    event MetadataCreated(
        bytes32 indexed recordId,
        bytes32 contentHash,
        string uri,
        uint256 version,
        address indexed owner,
        uint256 timestamp
    );

    event MetadataUpdated(
        bytes32 indexed recordId,
        bytes32 contentHash,
        string uri,
        uint256 version,
        address indexed updatedBy,
        uint256 timestamp
    );

    function create(bytes32 recordId, bytes32 contentHash, string calldata uri) external {
        require(items[recordId].owner == address(0), "exists");
        items[recordId] = Item({
            contentHash: contentHash,
            uri: uri,
            version: 1,
            owner: msg.sender,
            createdAt: block.timestamp,
            updatedAt: block.timestamp,
            updatedBy: msg.sender
        });
        emit MetadataCreated(recordId, contentHash, uri, 1, msg.sender, block.timestamp);
    }

    function update(bytes32 recordId, bytes32 newContentHash, string calldata uri) external {
        Item storage it = items[recordId];
        require(it.owner != address(0), "not found");
        require(msg.sender == it.owner, "not owner");
        it.version += 1;
        it.contentHash = newContentHash;
        it.uri = uri;
        it.updatedAt = block.timestamp;
        it.updatedBy = msg.sender;
        emit MetadataUpdated(recordId, newContentHash, uri, it.version, msg.sender, block.timestamp);
    }

    function get(bytes32 recordId) external view returns (Item memory) {
        return items[recordId];
    }
}