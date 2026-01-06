/* Tiny line chart (canvas 2d) */
window.renderLineChart = function(id, labels, values, brand){
  const canvas = document.getElementById(id);
  if(!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width = canvas.offsetWidth || 680;
  const H = canvas.height = canvas.height || 140;
  ctx.clearRect(0,0,W,H);
  // axes
  ctx.strokeStyle = 'rgba(255,255,255,0.2)';
  ctx.beginPath(); ctx.moveTo(40,10); ctx.lineTo(40,H-20); ctx.lineTo(W-10,H-20); ctx.stroke();
  // scaling
  const maxV = Math.max(100, ...values, 0); const minV = Math.min(...values, 0);
  const xStep = (W-60)/Math.max(1, values.length-1);
  const y = v => (H-20) - ( (v-minV)/(maxV-minV || 1) ) * (H-40);
  // line
  ctx.strokeStyle = '#5B8CFF'; ctx.lineWidth = 2; ctx.beginPath();
  values.forEach((v,i)=>{ const x = 40 + i*xStep; const yy = y(v); if(i===0) ctx.moveTo(x,yy); else ctx.lineTo(x,yy); });
  ctx.stroke();
  // points
  ctx.fillStyle = '#7aa2ff';
  values.forEach((v,i)=>{ const x = 40 + i*xStep; const yy = y(v); ctx.beginPath(); ctx.arc(x,yy,3,0,Math.PI*2); ctx.fill(); });
};
