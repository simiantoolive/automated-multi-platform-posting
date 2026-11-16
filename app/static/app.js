const labels={facebook:"Facebook Pages",linkedin:"LinkedIn",x:"X / Twitter",mastodon:"Mastodon",bluesky:"Bluesky"};
const icons={facebook:"f",linkedin:"in",x:"𝕏",mastodon:"m",bluesky:"☁"};
let state=null,busy=false;
const selected=new Set();
const el=id=>document.getElementById(id);
function notice(message,error=false){el("notice").hidden=!message;el("notice").textContent=message;el("notice").className=error?"error":""}
async function api(path,method="GET",body){
 const response=await fetch("/ui"+path,{method,credentials:"same-origin",headers:{"Content-Type":"application/json",...(state?{"X-CSRF-Token":state.csrf_token}:{})},...(body?{body:JSON.stringify(body)}:{})});
 const data=await response.json();
 if(!response.ok){const detail=data.detail;throw new Error(Array.isArray(detail)?detail.map(x=>x.msg).join("; "):detail||"Request failed.")}
 return data;
}
function updateComposer(){
 if(!state)return;
 const names=state.accounts.filter(a=>a.connected&&selected.has(a.platform)).map(a=>a.platform);
 const complete=names.length>0,text=el("message").value;
 el("chars").textContent=text.length+" / 200";
 el("publish").disabled=busy||!complete||!text.trim();
 const targets=names.length+" account"+(names.length===1?"":"s");
 el("publish").textContent=busy?"Working…":!complete?"Select an account to continue":(state.mode==="mock"?"Simulate posting to ":"Publish to ")+targets+" ↗";
 el("publish-help").textContent=!complete?"Connect and select at least one account.":state.mode==="mock"?"Demo only. No real posts will be created.":"This will create real posts only on your selected accounts.";
 el("destinations").textContent=names.length?names.map(name=>labels[name]).join(", "):"No accounts selected";
}
function render(){
 const mock=state.mode==="mock";
 el("mode").textContent=mock?"●  MOCK MODE · No real posts":"●  REAL MODE · Live publishing";
 el("mode").className="badge"+(mock?"":" real");
 el("connect-note").textContent=mock?"Connect any demo accounts, then select where to post. No login is needed.":"Connect any accounts and select where to post. One account is enough.";
 el("count").textContent=state.accounts.filter(a=>a.connected).length+" / 5 connected";
 el("accounts").replaceChildren();
 state.accounts.forEach(a=>{
  const row=document.createElement("div");row.className="account";
  const checkbox=document.createElement("input");checkbox.type="checkbox";checkbox.className="account-select";
  checkbox.checked=a.connected&&selected.has(a.platform);checkbox.disabled=busy||!a.connected;
  checkbox.setAttribute("aria-label","Publish to "+labels[a.platform]);
  checkbox.onchange=()=>{if(checkbox.checked)selected.add(a.platform);else selected.delete(a.platform);updateComposer()};
  const icon=document.createElement("span");icon.className="platform-icon "+a.platform;icon.textContent=icons[a.platform];
  const info=document.createElement("div");info.className="account-info";
  const name=document.createElement("div");name.className="account-name";name.textContent=labels[a.platform];
  const status=document.createElement("div");status.className="account-status"+(a.connected?" linked":"");
  status.textContent=a.connected?a.label:a.expired?"Connection expired · reconnect":a.configured?"Not connected":"App setup needed from owner";
  info.append(name,status);
  const button=document.createElement("button");button.type="button";
  button.textContent=a.connected?"Disconnect":mock?"Connect demo":a.configured?"Connect":"Setup needed";
  button.disabled=busy||(!a.connected&&!a.configured);
  button.setAttribute("aria-label",button.textContent+" "+labels[a.platform]);
  button.onclick=async()=>{
   busy=true;render();notice("");
   try{
    if(a.connected) await api("/connections/"+a.platform,"DELETE");
    else {
     const data=await api("/connect/"+a.platform,"POST");
     if(data.redirect){window.location.assign(data.redirect);return}
     if(data.app_password_required){el("bluesky-form").hidden=false;el("handle").focus()}
    }
    await refresh();
   }catch(e){notice(e.message,true)}finally{busy=false;render()}
  };
  row.append(checkbox,icon,info,button);el("accounts").append(row);
 });
 el("page-choice").hidden=!state.pages.length;
 el("pages").replaceChildren();
 state.pages.forEach(p=>{const o=document.createElement("option");o.value=p.id;o.textContent=p.name;el("pages").append(o)});
 updateComposer();
}
async function refresh(){
 const previous=new Set(state?state.accounts.filter(a=>a.connected).map(a=>a.platform):[]);
 state=await api("/session");
 state.accounts.forEach(a=>{if(!a.connected)selected.delete(a.platform);else if(!previous.has(a.platform))selected.add(a.platform)});
 render();if(state.notice)notice(state.notice)
}
el("message").addEventListener("input",updateComposer);
el("cancel-bluesky").onclick=()=>{el("bluesky-form").hidden=true;el("password").value=""};
el("bluesky-form").onsubmit=async e=>{
 e.preventDefault();busy=true;render();notice("");
 try{await api("/bluesky","POST",{handle:el("handle").value,app_password:el("password").value});el("bluesky-form").hidden=true;await refresh();notice("Bluesky connected. No post has been published.")}
 catch(error){notice(error.message,true)}finally{el("password").value="";busy=false;render()}
};
el("choose-page").onclick=async()=>{
 try{await api("/facebook/page","POST",{page_id:el("pages").value});await refresh();notice("Facebook Page connected.")}
 catch(error){notice(error.message,true)}
};
el("publish-form").onsubmit=async e=>{
 e.preventDefault();
 if(busy)return;
 const targets=state.accounts.filter(a=>a.connected&&selected.has(a.platform)).map(a=>a.platform);
 if(!targets.length){notice("Select at least one connected account.",true);return}
 if(state.mode==="real"&&!window.confirm("Publish this message now to "+targets.map(name=>labels[name]).join(", ")+"?"))return;
 busy=true;render();notice("");
 try{
  const data=await api("/publish","POST",{message:el("message").value,platforms:targets});
  el("results-section").hidden=false;el("results").replaceChildren();
  el("result-summary").textContent=data.mode==="mock"?data.simulated_count+" simulated · 0 published":data.success_count+" published · "+data.failure_count+" failed";
  data.results.forEach(r=>{
   const card=document.createElement("article");card.className="result";
   const title=document.createElement("strong");title.textContent=labels[r.platform];
   const status=document.createElement("span");status.className="status";status.textContent=r.status;
   const description=document.createElement("p");description.textContent=r.error?r.error.message:r.mode==="mock"?"Demo only. Nothing was published.":r.warnings.join(" ")||"Platform acknowledged the post. Public accessibility is unverified.";
   card.append(title,status,description);
   if(r.posted_url&&/^https?:\/\//i.test(r.posted_url)){const a=document.createElement("a");a.href=r.posted_url;a.target="_blank";a.rel="noopener noreferrer";a.textContent="View post ↗";card.append(a)}
   el("results").append(card);
  });
  el("results-section").scrollIntoView({behavior:"smooth",block:"nearest"});
 }catch(error){notice(error.message,true)}finally{busy=false;render()}
};
refresh().catch(error=>notice(error.message,true));
