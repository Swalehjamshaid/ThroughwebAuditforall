let chart;
function renderScores(scores){
  const ctx = document.getElementById('scoreChart');
  const labels = Object.keys(scores).filter(k=>k!=='overall' && k!=='grade');
  const data = labels.map(k=>scores[k]);
  if(chart){ chart.destroy(); }
  chart = new Chart(ctx, {type:'bar', data:{labels, datasets:[{label:'Category Score', data, backgroundColor:'#2e86de'}]}, options:{scales:{y:{beginAtZero:true, max:100}}}});
  document.getElementById('scores').innerHTML = `<div class="alert alert-secondary">Overall: <b>${scores.overall?.toFixed? scores.overall.toFixed(1):scores.overall}</b> — Grade: <b>${scores.grade}</b></div>`
}
