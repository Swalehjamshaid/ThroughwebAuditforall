
(function(){
  const d = window.FFTECH_DATA || { score: 0, categories: {security:0,performance:0,seo:0,mobile:0,content:0} };
  // Overall donut
  const ov = document.getElementById('overallChart');
  if (ov && window.Chart) {
    new Chart(ov, {
      type: 'doughnut',
      data: { labels: ['Score','Remaining'],
        datasets: [{ data: [d.score, 100-d.score], backgroundColor:['#00ADB5','#2a2a2a'], borderWidth:0 }] },
      options: { circumference: 180, rotation: -90, cutout: '70%', plugins: { legend: { display:false } } }
    });
  }
  // Bar chart
  const bc = document.getElementById('barChart');
  if (bc && window.Chart) {
    new Chart(bc, {
      type: 'bar',
      data: { labels: ['Security','Performance','SEO','Mobile','Content'],
        datasets: [{ label:'Category Scores',
          data:[d.categories.security,d.categories.performance,d.categories.seo,d.categories.mobile,d.categories.content],
          backgroundColor:'#00ADB5' }] },
      options: { scales: { y: { min:0, max:100 } }, plugins:{ legend:{ display:false } } }
    });
  }
})();
