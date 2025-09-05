import os, json, time, hashlib, binascii, pathlib
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version

# ───────────────────── 설정 ─────────────────────
RPC_URL         = os.getenv("QUORUM_RPC", "http://rpcnode:8545")
PRIVATE_KEY     = os.getenv("PRIVATE_KEY")
AUTO_DEPLOY     = os.getenv("AUTO_DEPLOY", "false").lower() == "true"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
DATA_DIR        = pathlib.Path("/data")
CONTRACT_FILE   = DATA_DIR / "contract.json"  # { address, abi }
OBJECTS_DIR     = DATA_DIR / "objects"        # 로컬 JSON 저장(데모)

if not PRIVATE_KEY:
    raise RuntimeError("PRIVATE_KEY is required (demo only). Use a test key.")

w3 = Web3(Web3.HTTPProvider(RPC_URL))
acct = w3.eth.account.from_key(bytes.fromhex(PRIVATE_KEY[2:] if PRIVATE_KEY.startswith("0x") else PRIVATE_KEY))

app = FastAPI(title="Metadata dApp (Quorum, FastAPI)")
app.mount("/objects", StaticFiles(directory=str(OBJECTS_DIR), html=False), name="objects")
templates = Jinja2Templates(directory="templates")

# ───────────────────── 도우미 ─────────────────────
SOLC_VER = "0.8.20"
CONTRACT_SRC = (pathlib.Path("contracts")/"MetadataRegistry.sol").read_text()

def _install_solc_once():
    try:
        set_solc_version(SOLC_VER)
    except Exception:
        install_solc(SOLC_VER)
        set_solc_version(SOLC_VER)


def _compile_contract():
    _install_solc_once()
    out = compile_source(CONTRACT_SRC)
    _, artifact = out.popitem()
    return artifact["abi"], artifact["bin"]


def _load_or_deploy_contract():
    # 1) 캐시 파일 있으면 사용
    if CONTRACT_FILE.exists():
        data = json.loads(CONTRACT_FILE.read_text())
        return Web3.to_checksum_address(data["address"]), data["abi"]

    # 2) AUTO_DEPLOY면 배포
    if AUTO_DEPLOY:
        abi, bytecode = _compile_contract()
        ct = w3.eth.contract(abi=abi, bytecode=bytecode)
        tx = ct.constructor().build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": 6_000_000,
            "gasPrice": 0
        })
        signed = w3.eth.account.sign_transaction(tx, acct.key)
        rc = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.rawTransaction))
        addr = rc.contractAddress
        CONTRACT_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_FILE.write_text(json.dumps({"address": addr, "abi": abi}, indent=2))
        return Web3.to_checksum_address(addr), abi

    raise RuntimeError("Contract not found. Set AUTO_DEPLOY=true or provide /data/contract.json")


def _b32(hexstr: str) -> bytes:
    s = hexstr[2:] if hexstr.startswith("0x") else hexstr
    raw = binascii.unhexlify(s)
    if len(raw) != 32:
        raise ValueError("must be 32 bytes")
    return raw


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ───────────────────── 모델 ─────────────────────
class CreateReq(BaseModel):
    recordIdHex: Optional[str] = Field(None, description="0x + 64 hex (bytes32). 없으면 서버가 생성")
    json_text: Optional[str] = Field(None, description="저장할 JSON 문자열. 제공 시 contentHash는 서버가 계산하며, /objects에 저장")
    uri: Optional[str] = Field(None, description="외부 URI 직접 지정 시")

class UpdateReq(BaseModel):
    json_text: Optional[str] = None
    uri: Optional[str] = None

# ───────────────────── 시작 시 컨트랙트 준비 ─────────────────────
CONTRACT_ADDR, CONTRACT_ABI = _load_or_deploy_contract()
CT = w3.eth.contract(address=CONTRACT_ADDR, abi=CONTRACT_ABI)
OBJECTS_DIR.mkdir(parents=True, exist_ok=True)

# ───────────────────── UI ─────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(req: Request):
    return templates.TemplateResponse("index.html", {"request": req})

# ───────────────────── API ─────────────────────
@app.get("/api/health")
def health():
    return {
        "chainId": w3.eth.chain_id,
        "gasPrice": w3.eth.gas_price,
        "contract": CONTRACT_ADDR,
        "account": acct.address,
    }

@app.get("/api/address")
def addr():
    return {"contract": CONTRACT_ADDR}

@app.get("/api/metadata")
def list_metadata():
    # 이벤트 기반 간단 나열 (개발/소규모 용)
    created = CT.events.MetadataCreated.create_filter(fromBlock=0)
    updated = CT.events.MetadataUpdated.create_filter(fromBlock=0)
    items = {}
    for lg in created.get_all_entries():
        a = lg["args"]
        rid = a["recordId"].hex()
        items[rid] = {
            "recordId": rid,
            "contentHash": a["contentHash"].hex(),
            "uri": a["uri"],
            "version": int(a["version"]),
            "owner": a["owner"],
            "updatedBy": a["owner"],
            "updatedAt": int(a["timestamp"]),
            "createdAt": int(a["timestamp"]),
        }
    for lg in updated.get_all_entries():
        a = lg["args"]
        rid = a["recordId"].hex()
        if rid not in items:
            items[rid] = {}
        items[rid].update({
            "recordId": rid,
            "contentHash": a["contentHash"].hex(),
            "uri": a["uri"],
            "version": int(a["version"]),
            "updatedBy": a["updatedBy"],
            "updatedAt": int(a["timestamp"]),
        })
    # 최신순 정렬
    return {"items": sorted(items.values(), key=lambda x: x.get("updatedAt", 0), reverse=True)}

@app.get("/api/metadata/{recordIdHex}")
def get_one(recordIdHex: str):
    try:
        rid = _b32(recordIdHex)
    except Exception as e:
        raise HTTPException(400, f"invalid recordId: {e}")
    it = CT.functions.get(rid).call()
    if it[3] == "0x0000000000000000000000000000000000000000":
        raise HTTPException(404, "not found")
    return {
        "recordId": recordIdHex.lower(),
        "contentHash": Web3.to_hex(it[0]),
        "uri": it[1],
        "version": int(it[2]),
        "owner": it[3],
        "createdAt": int(it[4]),
        "updatedAt": int(it[5]),
        "updatedBy": it[6],
    }

@app.post("/api/metadata")
def create(req: CreateReq):
    # recordId 생성
    if req.recordIdHex:
        try:
            rid = _b32(req.recordIdHex)
        except Exception as e:
            raise HTTPException(400, f"invalid recordId: {e}")
    else:
        # 내용 기반 + 시간 salt
        seed = (req.json_text or str(time.time())).encode()
        rid = Web3.keccak(seed)

    # contentHash & uri 결정
    if req.json_text:
        raw = req.json_text.encode()
        ch_hex = _sha256_hex(raw)
        # 로컬 저장(데모): /objects/<rid>/v1.json
        rid_hex = Web3.to_hex(rid)[2:]
        target = OBJECTS_DIR / rid_hex / "v1.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(req.json_text)
        uri = f"{PUBLIC_BASE_URL}/objects/{rid_hex}/v1.json" if PUBLIC_BASE_URL else f"/objects/{rid_hex}/v1.json"
    elif req.uri:
        ch_hex = "0" * 64  # 알 수 없음(외부 URI만 제공시)
        uri = req.uri
    else:
        raise HTTPException(400, "json_text 또는 uri 중 하나는 필요")

    # 트랜잭션
    tx = CT.functions.create(rid, Web3.to_bytes(hexstr="0x"+ch_hex), uri).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 3_000_000,
        "gasPrice": 0
    })
    signed = w3.eth.account.sign_transaction(tx, acct.key)
    rc = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.rawTransaction))
    return {"txHash": rc.transactionHash.hex(), "recordId": Web3.to_hex(rid), "uri": uri}

@app.put("/api/metadata/{recordIdHex}")
def update(recordIdHex: str, req: UpdateReq):
    try:
        rid = _b32(recordIdHex)
    except Exception as e:
        raise HTTPException(400, f"invalid recordId: {e}")

    # 기존 버전 조회
    it = CT.functions.get(rid).call()
    if it[3] == "0x0000000000000000000000000000000000000000":
        raise HTTPException(404, "not found")
    current_ver = int(it[2])

    # 새 contentHash/URI
    if req.json_text:
        raw = req.json_text.encode()
        ch_hex = _sha256_hex(raw)
        rid_hex = recordIdHex[2:] if recordIdHex.startswith("0x") else recordIdHex
        target = OBJECTS_DIR / rid_hex / f"v{current_ver+1}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(req.json_text)
        uri = f"{PUBLIC_BASE_URL}/objects/{rid_hex}/v{current_ver+1}.json" if PUBLIC_BASE_URL else f"/objects/{rid_hex}/v{current_ver+1}.json"
    elif req.uri:
        ch_hex = "0" * 64
        uri = req.uri
    else:
        raise HTTPException(400, "json_text 또는 uri 중 하나는 필요")

    tx = CT.functions.update(rid, Web3.to_bytes(hexstr="0x"+ch_hex), uri).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 3_000_000,
        "gasPrice": 0
    })
    signed = w3.eth.account.sign_transaction(tx, acct.key)
    rc = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.rawTransaction))
    return {"txHash": rc.transactionHash.hex(), "recordId": recordIdHex, "newUri": uri}