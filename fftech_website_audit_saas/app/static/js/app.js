
// FF Tech – UI interactions
(function(){
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  console.log('FF Tech UI loaded. Dark:', prefersDark);
})();

// Chart.js helpers for gradient
function gradient(ctx, colorA, colorB){
  const g = ctx.createLinearGradient(0,0,0,220);
  g.addColorStop(0, colorA);
  g.addColorStop(1, colorB);
  return g;
}
