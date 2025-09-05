async function j(url, opt={}){
    const r = await fetch(url, Object.assign({headers:{'Content-Type':'application/json'}}, opt));
    if(!r.ok){ throw new Error(await r.text()); }
    return await r.json();
  }
  
  async function loadHealth(){
    try{ const h = await j('/api/health');
      document.getElementById('health').innerHTML =
        `chainId=<code>${h.chainId}</code>, gasPrice=<code>${h.gasPrice}</code>, contract=<code>${h.contract}</code>`;
    }catch(e){ document.getElementById('health').innerText = 'health error: '+e; }
  }
  
  async function refresh(){
    const out = document.getElementById('list'); out.innerHTML = 'loading...';
    try{
      const d = await j('/api/metadata');
      out.innerHTML = '';
      for(const it of d.items){
        const div = document.createElement('div'); div.className='card';
        div.innerHTML = `
          <div><b>recordId:</b> <code>${it.recordId}</code></div>
          <div><b>version:</b> ${it.version} <span class="muted">(owner: ${it.owner})</span></div>
          <div><b>contentHash:</b> <code>${it.contentHash}</code></div>
          <div><b>uri:</b> <a href="${it.uri}" target="_blank">${it.uri}</a></div>
          <div class="row" style="margin-top:8px">
            <textarea class="edit-json" placeholder="수정할 JSON (또는 아래 URI만 수정)"></textarea>
            <div style="width:320px">
              <input class="edit-uri" type="text" placeholder="새 URI (선택)" />
              <button class="btn-save">수정 트랜잭션</button>
              <div class="muted edit-out"></div>
            </div>
          </div>`;
        const btn = div.querySelector('.btn-save');
        btn.onclick = async () => {
          const jsonText = div.querySelector('.edit-json').value.trim();
          const uri = div.querySelector('.edit-uri').value.trim();
          const body = {};
          if(jsonText) body.json_text = jsonText; else if(uri) body.uri = uri; else { alert('JSON 또는 URI 중 하나는 필요'); return; }
          div.querySelector('.edit-out').innerText = 'updating...';
          try{
            const r = await j(`/api/metadata/${it.recordId}`, {method:'PUT', body: JSON.stringify(body)});
            div.querySelector('.edit-out').innerText = `tx: ${r.txHash}`;
            await refresh();
          }catch(e){ div.querySelector('.edit-out').innerText = e; }
        };
        out.appendChild(div);
      }
    }catch(e){ out.innerText = 'list error: '+e; }
  }
  
  document.getElementById('btn-create').onclick = async () => {
    const jsonText = document.getElementById('create-json').value.trim();
    const recId = document.getElementById('create-id').value.trim();
    const uri = document.getElementById('create-uri').value.trim();
    const body = {};
    if(recId) body.recordIdHex = recId;
    if(jsonText) body.json_text = jsonText; else if(uri) body.uri = uri; else { alert('JSON 또는 URI 중 하나는 필요'); return; }
    const out = document.getElementById('create-out'); out.innerText = 'creating...';
    try{
      const r = await j('/api/metadata', {method:'POST', body: JSON.stringify(body)});
      out.innerText = `recordId=${r.recordId}, tx=${r.txHash}`;
      await refresh();
    }catch(e){ out.innerText = e; }
  };
  
  document.getElementById('btn-refresh').onclick = refresh;
  
  loadHealth().then(refresh);