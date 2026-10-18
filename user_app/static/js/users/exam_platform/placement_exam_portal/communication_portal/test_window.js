history.pushState(null,null,location.href); window.onpopstate=()=>history.go(1);
        document.oncontextmenu=()=>false;

        let failCount = 0; const FAIL_THRESHOLD = 3; let isOverlayShown = false;
        function updateUI(status) {
            const icon = document.getElementById('wifiIcon'); const overlay = document.getElementById('offlineOverlay');
            icon.classList.remove('wifi-good', 'wifi-low', 'wifi-bad');
            if (status === 'offline') { icon.classList.add('wifi-bad'); icon.title = "Connection: Lost"; if (!isOverlayShown) { overlay.classList.add('show'); isOverlayShown = true; } }
            else if (status === 'low') { icon.classList.add('wifi-low'); icon.title = "Connection: Weak"; if (isOverlayShown) { overlay.classList.remove('show'); isOverlayShown = false; } }
            else { icon.classList.add('wifi-good'); icon.title = "Connection: Stable"; if (isOverlayShown) { overlay.classList.remove('show'); isOverlayShown = false; } }
        }
        async function checkConnection() {
            if (!navigator.onLine) { failCount = FAIL_THRESHOLD + 1; updateUI('offline'); return; }
            const controller = new AbortController(); const timeoutId = setTimeout(() => controller.abort(), 10000);
            try { const start = Date.now(); const response = await fetch('/api/network-check?t=' + start, { method: 'GET', cache: "no-store", signal: controller.signal }); clearTimeout(timeoutId);
                if (response.ok) { const duration = Date.now() - start; failCount = 0; if (duration > 2000) updateUI('low'); else updateUI('good'); } else { updateUI('low'); }
            } catch (error) { failCount++; if (failCount >= FAIL_THRESHOLD) updateUI('offline'); else updateUI('low'); }
        }
        window.addEventListener('offline', () => { failCount = FAIL_THRESHOLD + 1; updateUI('offline'); });
        window.addEventListener('online', () => { checkConnection(); });
        setInterval(checkConnection, 8000); checkConnection();

        let quill=null, recognition=null, transcript="", data={}, curSec=0, curQ=0, qs=[], submIds=[], revIds=[], secStatus=[];
        let sTime=0, gTime=0, recTime=0, sInt, gInt, rInt, rSec=0, mRec, chunks=[], thinkInt, recTimer;
        let lastAudioUrl = "";
        const key = document.getElementById('testKey').value; const csrf = document.getElementById('csrfToken').value;

        let authLossHandled = false;
        async function handleAuthLoss(res) {
            if (!res || res.status !== 401) return false;
            if (authLossHandled) return true;
            authLossHandled = true;
            let loginUrl = '/user_login';
            try { const body = await res.clone().json(); if (body && body.login_url) loginUrl = body.login_url; } catch (e) {}
            alert("You have been signed out, so this assessment cannot continue. Please log in again and resume from your dashboard.");
            window.sppExamLeaving = true;
            if (typeof window.sppMarkExamFinished === 'function') window.sppMarkExamFinished();
            window.location.replace(loginUrl + '?next=' + encodeURIComponent(window.location.pathname));
            return true;
        }

        if(window.SpeechRecognition || window.webkitSpeechRecognition) {
            recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
            recognition.continuous=true;
            recognition.onresult=e=>{ for(let i=e.resultIndex; i<e.results.length; ++i) if(e.results[i].isFinal) transcript+=e.results[i][0].transcript; };
            recognition.onend = () => {
                if(mRec && mRec.state === 'recording'){
                    try{ recognition.start(); }catch(e){}
                }
            };
            recognition.onerror = (e) => { console.warn('Speech recognition error:', e.error); };
        }

        window.onload = async () => {
            try {
                const res = await fetch(`/api/get-test-data/${key}`);
                if(await handleAuthLoss(res)) return;
                if(!res.ok) { window.sppExamLeaving = true; if (typeof window.sppMarkExamFinished === 'function') window.sppMarkExamFinished(); window.location.replace('/'); return; }
                data = await res.json();
                if(data.answers) { submIds = Object.keys(data.answers); }
                gTime = parseInt(document.getElementById('twOverallTime').value);
                secStatus = new Array(data.sections.length).fill(false);
                if(data.sections.length) {
                    let rS=parseInt(document.getElementById('resSec').value)||0; let rQ=parseInt(document.getElementById('resQ').value)||0;
                    for(let i=0; i<rS; i++) secStatus[i] = true; loadSec(rS, rQ); startG();
                }
            } catch(e) { console.error("Init failed", e); }
        };

        function loadSec(idx, qIdx=0) {
            clearInterval(sInt); curSec=idx; const s=data.sections[idx];
            document.getElementById('mainContent').classList.add('hidden'); document.getElementById('introPanel').classList.remove('hidden');
            document.getElementById('introTitle').innerText=s.section_title;
            document.getElementById('introDesc').innerText=s.section_instruction || "Please read the questions carefully.";
            qs=data.questions.filter(q=>q.section_name===s.section_name);
            if(qs.length===0) { if(idx<data.sections.length-1) loadSec(idx+1); else showSum(); return; }
            if (qIdx === 0 && idx === 0) curQ = 0; else if (qIdx > 0 && qIdx < qs.length) curQ = qIdx; else { curQ = 0; for(let i=0; i<qs.length; i++) if(!submIds.includes(String(qs[i].id))) { curQ=i; break; } }
            sTime=s.section_duration_seconds;
        }

        function startSectionQuestions() {
            document.getElementById('introPanel').classList.add('hidden'); document.getElementById('mainContent').classList.remove('hidden');
            document.getElementById('secName').innerText=data.sections[curSec].section_name.replace(/_/g,' ');
            startS(); renderPag(); loadQ();
        }

        function renderPag() {
            const p=document.getElementById('pages'); const f=document.getElementById('fGrid'); p.innerHTML=''; f.innerHTML='';
            qs.forEach((q,i) => {
                let qidStr = String(q.id); let status = submIds.includes(qidStr) ? 'done' : (revIds.includes(qidStr) ? 'revisit' : '');
                let cls = `page-dot ${i===curQ?'active':status}`;
                let d=document.createElement('div'); d.className=cls; d.innerText=i+1; d.onclick=()=>{curQ=i;loadQ();}; p.appendChild(d);
                let g=document.createElement('div'); g.className=`page-dot ${status} ${i===curQ?'active':''}`; g.innerText=i+1; g.style.width='100%'; g.onclick=()=>{curQ=i;loadQ();}; f.appendChild(g);
            });
            document.getElementById('attCount').innerText=`${qs.filter(q=>submIds.includes(String(q.id))).length}/${qs.length}`;
            const bBtn = document.getElementById('revBtn'); const icon = bBtn.querySelector('i'); const txt = bBtn.querySelector('span');
            if(revIds.includes(String(qs[curQ].id))) { bBtn.classList.add('active'); icon.className = "fas fa-bookmark"; txt.innerText = "Marked"; } else { bBtn.classList.remove('active'); icon.className = "far fa-bookmark"; txt.innerText = "Mark for Review"; }
        }

        function pad(n) { return n < 10 ? '0' + n : n; }

        function loadQ() {
            if(mRec && mRec.state!=='inactive') mRec.stop(); clearInterval(thinkInt); clearInterval(rInt); clearTimeout(recTimer);
            const q=qs[curQ]; const qidStr = String(q.id);
            const isSecDone = secStatus[data.sections.findIndex(s => s.section_name === q.section_name)];
            const isSubmitted = submIds.includes(qidStr);
            const mainContent = document.getElementById('mainContent'); const audContainer = document.getElementById('qMedia'); const qTextDiv = document.getElementById('qText');
            document.getElementById('qNum').innerText=curQ+1; document.getElementById('qInst').innerText=q.instruction_text||"";

            if(q.question_type === 'FILL_BLANK') {
                mainContent.classList.add('full-mode'); audContainer.classList.add('hidden'); renderFIB(q, qTextDiv);
            } else {
                mainContent.classList.remove('full-mode');
                if (q.media_url) {
                    audContainer.classList.remove('hidden');
                    qTextDiv.innerHTML = ''; if(q.question_text) qTextDiv.innerHTML = q.question_text;
                    if (lastAudioUrl !== q.media_url) { lastAudioUrl = q.media_url; document.getElementById('audioPlayer').src = q.media_url; }
                } else {
                    audContainer.classList.add('hidden'); document.getElementById('audioPlayer').pause();
                    qTextDiv.innerHTML = q.question_text;
                }
            }

            const recUI = document.getElementById('recUI'); const interactiveUI = document.getElementById('interactiveUI'); const alertBox = document.getElementById('alertBox');
            recUI.classList.add('hidden'); interactiveUI.innerHTML=''; stopRecUI();

            if (isSecDone) {
                alertBox.classList.remove('hidden'); alertBox.innerText = "Section Time Expired. View Only.";
                interactiveUI.style.pointerEvents = 'none'; interactiveUI.style.opacity = '0.6'; if(quill) quill.disable();
                const fibInputs = qTextDiv.querySelectorAll('input'); fibInputs.forEach(i => i.disabled = true);
            } else {
                alertBox.classList.add('hidden'); interactiveUI.style.pointerEvents = 'auto'; interactiveUI.style.opacity = '1';
                if(q.question_type==='THINK_SPEAK') startThink(q, isSubmitted); else if(['SPEAK','LISTEN_SPEAK'].includes(q.question_type)) setupRec(q, isSubmitted);
                else if(['MCQ','COMPREHENSION'].includes(q.question_type)) setupMCQ(q, isSubmitted, qidStr.endsWith('_0')); else if(q.question_type==='WRITING') setupWrite(q, isSubmitted);
            }
            renderPag();
        }

        function renderFIB(q, container) {
            let saved = {}; try { if(data.answers && data.answers[String(q.id)]) saved = JSON.parse(data.answers[String(q.id)]); } catch(e) { saved = {0: data.answers && data.answers[String(q.id)] ? data.answers[String(q.id)] : ""}; }
            let blankIndex = 0; const html = q.question_text.replace(/_{2,}/g, (match) => { const val = saved[blankIndex] || ''; const inputHtml = `<input type="text" class="inline-input" data-idx="${blankIndex}" value="${val}" oninput="handleFIBInput(this)" onkeydown="handleFIBKey(event, this)" placeholder="Answer" autocomplete="off" />`; blankIndex++; return inputHtml; }); container.innerHTML = html;
        }
        window.handleFIBInput = function(el) { const inputs = document.querySelectorAll('#qText input[data-idx]'); let ansObj = {}; inputs.forEach(inp => { ansObj[inp.getAttribute('data-idx')] = inp.value; }); sub('text', JSON.stringify(ansObj)); };
        window.handleFIBKey = function(e, el) { if(e.key === 'Enter') { e.preventDefault(); const inputs = Array.from(document.querySelectorAll('#qText .inline-input')); const currIdx = inputs.indexOf(el); if(currIdx < inputs.length - 1) inputs[currIdx + 1].focus(); } };

        function setupMCQ(q, isSubmitted, isIntro) {
            let h = ""; if (isIntro) h += `<div style="font-size:16px; font-weight:bold; margin-bottom:15px; color:#333;">${q.question_text}</div>`;
            h += `<div class="option-header">${q.options_title || "Choose the best option:"}</div>`;
            const qidStr = String(q.id); const savedAns = data.answers && data.answers[qidStr] ? data.answers[qidStr] : null;
            ['a','b','c','d'].forEach(o=>{ if(q[`option_${o}`]) { const isChecked = savedAns === o ? 'checked' : ''; const dis = isSubmitted ? 'disabled' : '';
            h+=`<label class="mcq-label"><input type="radio" name="mcq" value="${o}" ${isChecked} ${dis} onchange="sub('mcq',this.value)"> ${q[`option_${o}`]}</label>`; } });
            interactiveUI.innerHTML=h;
        }

        function setupRec(q, isSubmitted) {
            const recUI = document.getElementById('recUI'); recUI.classList.remove('hidden'); const maxMins = Math.floor(q.recording_time_seconds / 60); const maxSecs = q.recording_time_seconds % 60; document.getElementById('maxTimeDisplay').innerText = `${pad(maxMins)}:${pad(maxSecs)}`;
            const container = document.getElementById('recActionContainer');
            container.innerHTML = `<button id="btnAction" class="btn-record" onclick="handleRecClick()">Start Audio Recording</button>`;
            if(isSubmitted) {
                document.getElementById('recAlert').style.cssText = 'background:#d4edda;border-color:#c3e6cb;color:#155724';
                document.getElementById('recAlert').innerHTML = '<i class="fas fa-check-circle"></i> Response saved.';
                container.innerHTML = `<div class="text-success" style="font-size:16px; padding:10px;"><i class="fas fa-check-circle"></i> Response Saved</div>`;
            } else {
                document.getElementById('recAlert').style.cssText = 'background:#fffcf0;color:#856404';
                document.getElementById('recAlert').innerHTML = '<i class="fas fa-info-circle"></i> Start recording whenever ready';
                document.getElementById('btnAction').disabled = false;
            }
            document.getElementById('micIcon').classList.remove('active'); rSec=0; document.getElementById('recTimerLabel').innerText="Recording Time 00:00 Minutes";
        }
        function handleRecClick() { const btn=document.getElementById('btnAction'); if(btn.innerText==="Start Audio Recording" || btn.innerText==="Retry Recording") startRecording(); else if(btn.innerText==="Stop Recording") stopRecording(); }

        async function startRecording() {
            try {
                const s=await navigator.mediaDevices.getUserMedia({audio:true});
                mRec=new MediaRecorder(s);
                chunks=[];

                transcript = "";

                if(recognition){
                    try{ recognition.abort(); }catch(e){}
                    setTimeout(()=>{ try{ recognition.start(); }catch(e){} }, 120);
                }
                mRec.ondataavailable=e=>{if(e.data.size>0)chunks.push(e.data)};
                mRec.onstop=()=>{
                    if(recognition){ try{ recognition.stop(); }catch(e){} }
                    setTimeout(()=>{
                        sub('audio',new Blob(chunks,{type:'audio/webm'}),transcript);
                    }, 450);
                };
                mRec.start(1000);
                document.getElementById('btnAction').innerText="Stop Recording"; document.getElementById('btnAction').classList.add('stop'); document.getElementById('micIcon').classList.add('active');
                rInt=setInterval(()=>{rSec++;recTime++;const m=Math.floor(rSec/60),s=rSec%60;document.getElementById('recTimerLabel').innerText=`Recording Time ${pad(m)}:${pad(s)} Minutes`;if(rSec>=qs[curQ].recording_time_seconds)stopRecording()},1000);
            } catch(e){alert("Mic Error: "+e.message)}
        }
        function stopRecording() {
            if(mRec&&mRec.state==='recording'){ mRec.stop(); stopRecUI(); const container = document.getElementById('recActionContainer'); container.innerHTML = `<div class="text-success" style="font-size:16px; padding:10px;"><i class="fas fa-spinner fa-spin"></i> Saving...</div>`; }
        }
        function stopRecUI() { clearInterval(rInt); clearTimeout(recTimer); document.getElementById('micIcon').classList.remove('active'); document.getElementById('btnAction')?.classList.remove('stop'); }
        function setupWrite(q, isSubmitted) {
            const limit = q.word_limit || 0; document.getElementById('interactiveUI').innerHTML=`<div style="border:1px solid #ccc;border-radius:4px;background:#fff;"><div id="editor-container" style="height:350px;"></div><div id="wordCountBox" style="padding:5px;text-align:right;font-size:12px;">Words: 0 ${limit?'/ '+limit:''}</div></div>`;
            quill=new Quill('#editor-container',{theme:'snow',placeholder:'Type response...'}); if(data.answers&&data.answers[String(q.id)]) quill.root.innerHTML=data.answers[String(q.id)]; if(isSubmitted) quill.disable();
            quill.on('text-change',()=>{ const c=quill.getText().trim().split(/\s+/).length; document.getElementById('wordCountBox').innerText=`Words: ${c} ${limit?'/ '+limit:''}`; if(limit&&c>limit){ document.getElementById('wordCountBox').style.color='red'; quill.history.undo(); } else { document.getElementById('wordCountBox').style.color='#333'; sub('text',quill.root.innerHTML); } });
        }
        function startThink(q, isSubmitted) { setupRec(q,isSubmitted); if(isSubmitted) return; document.getElementById('btnAction').disabled=true; let t=q.thinking_time_seconds; thinkInt=setInterval(()=>{t--;document.getElementById('recAlert').innerText=`Thinking Time: ${t}s`;if(t<=0){clearInterval(thinkInt);document.getElementById('btnAction').disabled=false;document.getElementById('btnAction').innerText="Start Audio Recording";startRecording()}},1000); }
        async function nextQ() {
            if(document.getElementById('btnAction') && document.getElementById('btnAction').classList.contains('stop')){stopRecording();await new Promise(r=>setTimeout(r,800));}
            if(curQ<qs.length-1){curQ++;loadQ()}else{secStatus[curSec]=true;if(curSec<data.sections.length-1)loadSec(curSec+1);else showSum()}
        }

        async function sub(type,val,trans="") {
            if(secStatus[curSec])return; const qidStr=String(qs[curQ].id); const fd=new FormData();
            fd.append('test_key',key); fd.append('_csrf_token',csrf); fd.append('question_id',qidStr); fd.append('section_name',qs[curQ].section_name);
            fd.append('type',type); fd.append('sec_idx',curSec); fd.append('q_idx',curQ); fd.append('rec_time',recTime);

            fd.append('session_token', document.getElementById('sessionToken').value);

            if(type==='audio'){ fd.append('file',val); fd.append('transcription',trans); }
            else if(type==='mcq') { fd.append('value', val); }
            else if(type==='text') { fd.append('value', val); }

            if(!data.answers)data.answers={}; data.answers[qidStr]=val;
            try {
                const res = await fetch('/api/submit-answer',{method:'POST',body:fd});

                if(await handleAuthLoss(res)) return;

                if(res.status === 403) {
                    alert("Security Warning: This test session has been terminated because a new window was opened. You will be redirected.");
                    window.location.reload();
                    return;
                }

                if(type === 'audio') {
                    const container = document.getElementById('recActionContainer');
                    if(res.ok) {
                        if(container) container.innerHTML = `<div class="text-success" style="font-size:16px; padding:10px;"><i class="fas fa-check-circle"></i> Response Saved</div>`;
                        document.getElementById('recAlert').style.cssText = 'background:#d4edda;border-color:#c3e6cb;color:#155724';
                        document.getElementById('recAlert').innerHTML = '<i class="fas fa-check-circle"></i> Response saved.';
                        if(!submIds.includes(qidStr)) submIds.push(qidStr);
                        renderPag();
                    } else {
                         if(container) container.innerHTML = `<button id="btnAction" class="btn-record" onclick="handleRecClick()">Retry Recording</button>`;
                         alert("Save failed. Please check connection.");
                    }
                } else {
                    if(!submIds.includes(qidStr)) submIds.push(qidStr);
                    renderPag();
                }
            } catch(e) { console.error("Submit error", e); }
        }
        async function toggleRev() { const qid=String(qs[curQ].id); if(revIds.includes(qid))revIds=revIds.filter(i=>i!==qid);else revIds.push(qid); renderPag(); }

        function showSum() {
            document.getElementById('modal').classList.add('active');
            const tot = data.questions.length; const att = submIds.length; const rev = revIds.length; const una = tot - att;
            document.getElementById('sumTotalQ').innerText = tot;
            document.getElementById('valAtt').innerText = att; document.getElementById('valRev').innerText = rev; document.getElementById('valUna').innerText = una;
            document.getElementById('remTime').innerText = document.getElementById('globTimer').innerText;
            const pAtt = (att / tot) * 100 || 0;
            document.getElementById('mainDonut').style.background = `conic-gradient(var(--blue-chart) 0% ${pAtt}%, var(--grey-chart) ${pAtt}% 100%)`;
            let tbody = "";
            data.sections.forEach((sec, idx) => {
                const secQs = data.questions.filter(q => q.section_name === sec.section_name);
                const sTot = secQs.length; const sAtt = secQs.filter(q => submIds.includes(String(q.id))).length; const pct = sTot > 0 ? (sAtt / sTot) * 100 : 0;
                let timeDisplay = "00:00:00";
                if(idx === curSec) timeDisplay = document.getElementById('secTimer').innerText; else if(!secStatus[idx]) timeDisplay = "Pending"; else timeDisplay = "Completed";
                tbody += `<tr><td>${idx+1}.</td><td><div class="sec-name-col">${sec.section_title}</div><div class="sec-time-sub">Remaining Time: ${timeDisplay}</div></td><td><div class="progress-wrapper"><div class="progress-bg"><div class="progress-fill" style="width:${pct}%">${sAtt}</div></div><div class="prog-text">Total: ${sTot} Questions</div></div></td></tr>`;
            });
            document.getElementById('secTableBody').innerHTML = tbody;
        }

        function closeSum() { document.getElementById('modal').classList.remove('active'); }
        async function confirmFinish() {
            try {
                const res = await fetch('/finish-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                    body: JSON.stringify({
                        test_key: key,
                        round_name: document.getElementById('roundName').value,
                        course_code: document.getElementById('courseCode').value,
                        unique_code: document.getElementById('uniqueCode').value
                    })
                });
                if (await handleAuthLoss(res)) return;
                const d = await res.json();
                if (!res.ok || d.status === 'error') {
                    alert(d.message || "Could not submit the test. Please check your connection and try again.");
                    return;
                }
                if (d.redirect) {
                    window.sppExamLeaving = true;
                    if (typeof window.sppMarkExamFinished === 'function') window.sppMarkExamFinished();
                    window.location.replace(d.redirect);
                }
            } catch (e) { alert("Error finishing test: " + e); }
        }
        function startS() { clearInterval(sInt); sTime=Number(sTime); if(!isFinite(sTime)||sTime<=0){document.getElementById('secTimer').innerText='--:--';return;} sInt=setInterval(()=>{sTime--;let m=Math.floor(sTime/60),s=sTime%60;document.getElementById('secTimer').innerText=`${m}:${s<10?'0':''}${s}`;if(sTime<=0){clearInterval(sInt);secStatus[curSec]=true;if(curSec<data.sections.length-1)loadSec(curSec+1);else showSum()}},1000); }
        function startG() { clearInterval(gInt); gTime=Number(gTime); if(!isFinite(gTime)||gTime<=0){document.getElementById('globTimer').innerText='--:--';return;} gInt=setInterval(()=>{gTime--;let m=Math.floor(gTime/60),s=gTime%60;document.getElementById('globTimer').innerText=`${m}:${s<10?'0':''}${s}`;if(gTime<=0)confirmFinish()},1000); }
        function togFilter() { const b=document.getElementById('filterBox'); b.style.display=b.style.display==='block'?'none':'block'; }
        window.onclick=e=>{if(!e.target.closest('.filter-wrap'))document.getElementById('filterBox').style.display='none'}

(function () {
    var el = document.getElementById('testKey');
    if (!el) return;
    var key = el.value;
    var url = '/api/comm-heartbeat/' + encodeURIComponent(key);

    function beat() {
        fetch(url, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .catch(function () {});
    }
    beat();
    setInterval(beat, 15000);
})();

(function () {
    window.markCommTestFinished = function () {
        if (typeof window.sppMarkExamFinished === 'function') window.sppMarkExamFinished();
    };
})();

(function () {
    var btn = document.getElementById('twFullscreen');
    if (!btn) return;

    function sync() {
        var on = !!document.fullscreenElement;
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        btn.title = on ? 'Exit full screen' : 'Full screen';
        var i = btn.querySelector('i');
        if (i) i.className = on ? 'fas fa-compress' : 'fas fa-expand';
    }

    btn.addEventListener('click', function () {
        if (document.fullscreenElement) {
            if (document.exitFullscreen) document.exitFullscreen().catch(function () {});
        } else if (document.documentElement.requestFullscreen) {
            document.documentElement.requestFullscreen().catch(function () {});
        }
    });

    document.addEventListener('fullscreenchange', sync);
    sync();
})();
