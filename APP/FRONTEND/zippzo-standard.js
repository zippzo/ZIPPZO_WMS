
/* ZIPPZO FRONTEND STANDARD LAYER */
(function(){
  function hideDropping(){
    document.querySelectorAll('a,button,[role="menuitem"],.nav').forEach(function(el){
      var t=(el.textContent||'').trim().toLowerCase();
      var h=(el.getAttribute('href')||'').toLowerCase();
      var o=(el.getAttribute('onclick')||'').toLowerCase();
      if(t==='dropping' || h.includes('dropping.html') || o.includes('opendropping')){
        el.style.display='none';
      }
    });
  }
  function markActive(){
    var path=(location.pathname||'').split('/').pop().toLowerCase();
    document.querySelectorAll('a[href]').forEach(function(a){
      var href=(a.getAttribute('href')||'').split('/').pop().toLowerCase();
      if(href && href===path && !href.includes('dropping')){
        a.classList.add('active');
      }
    });
  }
  document.addEventListener('DOMContentLoaded',function(){
    hideDropping(); markActive();
    new MutationObserver(hideDropping).observe(document.body,{childList:true,subtree:true});
  });
})();
