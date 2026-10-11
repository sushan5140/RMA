const status=document.getElementById('status'), links=document.getElementById('links');
async function refresh(){const data=await chrome.storage.local.get({reels:[]}); links.value=data.reels.join('\n');}
document.getElementById('save').addEventListener('click',async()=>{
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  try{
    const u=new URL(tab?.url || '');
    if(!['instagram.com','www.instagram.com'].includes(u.hostname)) throw Error('Open Instagram first');
    const match=u.pathname.match(/^\/reel\/([A-Za-z0-9_-]+)\/?$/);
    if(!match) throw Error('Open an individual reel URL (/reel/...) first');
    const url='https://www.instagram.com/reel/'+match[1]+'/';
    const data=await chrome.storage.local.get({reels:[]});
    if(!data.reels.includes(url)) data.reels.push(url);
    await chrome.storage.local.set({reels:data.reels});
    status.textContent='Saved: '+url;
  }catch(e){status.textContent=e.message;}
  await refresh();
});
document.getElementById('copy').addEventListener('click',async()=>{
  await navigator.clipboard.writeText(links.value);status.textContent='Copied links';
});
document.getElementById('clear').addEventListener('click',async()=>{
  if(!confirm('Clear all saved links?')) return;
  await chrome.storage.local.set({reels:[]});status.textContent='Cleared';await refresh();
});
refresh();