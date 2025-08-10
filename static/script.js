// Global chart refs
let chartAvgTime, chartCompletion, chartDevice, chartTrend;
let currentCourse = "__all";

// helpers
const $ = (id) => document.getElementById(id);

async function fetchJSON(path){ const r = await fetch(path); return await r.json(); }

async function loadAll(){
  // summary KPIs
  const s = await fetchJSON("/api/summary");
  $("kpi-total").textContent = s.total_users ?? "—";
  $("kpi-popular").textContent = s.most_popular_course ?? "—";
  $("kpi-avg").textContent = s.avg_time_overall ?? "—";
  // most/least
  const ml = await fetchJSON("/api/most_least_time");
  $("kpi-mostleast").textContent = ml.most_time_course ? `${ml.most_time_course} / ${ml.least_time_course}` : "—";

  // avg time per course (populate course filter)
  const avg = await fetchJSON("/api/avg_time_per_course");
  populateCourseFilter(Object.keys(avg));
  renderAvgTimeChart(avg);

  // completion distribution
  const comp = await fetchJSON("/api/summary"); // completion counts included
  renderCompletionChart(comp.completion_counts || {});

  // device usage
  const dev = await fetchJSON("/api/device_usage");
  renderDeviceChart(dev || {});

  // monthly trends
  const trend = await fetchJSON("/api/monthly_trends");
  renderTrendChart(trend.overall || {});

  // completion percentages table
  const compPerc = await fetchJSON("/api/course_completion_percentages");
  populateCompletionTable(compPerc);

  // raw (show latest 200)
  const raw = await fetchJSON("/api/raw");
  populateRawTable(raw.slice(0, 200));
}

// ---------- population helpers ----------
function populateCourseFilter(courses){
  const sel = $("courseFilter");
  sel.innerHTML = '<option value="__all">All</option>';
  courses.forEach(c=>{
    const opt = document.createElement("option");
    opt.value = c; opt.textContent = c; sel.appendChild(opt);
  });
}

function populateCompletionTable(data){
  const tbody = document.querySelector("#completionTable tbody");
  tbody.innerHTML = "";
  Object.entries(data).sort((a,b)=> b[1].completion_percent - a[1].completion_percent).forEach(([course, obj])=>{
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${course}</td><td>${obj.total}</td><td>${obj.completed}</td><td>${obj.completion_percent}%</td>`;
    tbody.appendChild(tr);
  });
}

function populateRawTable(rows){
  const tbody = document.querySelector("#rawTable tbody");
  tbody.innerHTML = "";
  rows.forEach(r=>{
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.userid||""}</td><td>${r.techno||""}</td><td>${r.accessdate||""}</td>
                    <td>${r.completionstatus||""}</td><td>${r.time_spent||""}</td><td>${r.device||""}</td><td>${r.country||""}</td>`;
    tbody.appendChild(tr);
  });
}

// ---------- chart renderers ----------
function renderAvgTimeChart(avgData){
  const labels = Object.keys(avgData);
  const values = Object.values(avgData);
  const ctx = document.getElementById("chartAvgTime").getContext("2d");
  if(chartAvgTime) chartAvgTime.destroy();
  chartAvgTime = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets: [{ label:"Avg time (mins)", data:values, backgroundColor:"#1976d2" }]},
    options: {
      onClick: (evt, elems) => {
        if(elems.length){
          const idx = elems[0].index;
          const course = labels[idx];
          applyCourseFilter(course);
        }
      },
      plugins: { legend:{display:false} },
      responsive:true
    }
  });
}

function renderCompletionChart(compData){
  const labels = Object.keys(compData);
  const values = Object.values(compData);
  const ctx = document.getElementById("chartCompletion").getContext("2d");
  if(chartCompletion) chartCompletion.destroy();
  chartCompletion = new Chart(ctx, {
    type: "pie",
    data: { labels, datasets:[{ data: values, backgroundColor:["#4caf50","#ff9800","#f44336"] }]},
    options:{ responsive:true }
  });
}

function renderDeviceChart(deviceData){
  const labels = Object.keys(deviceData);
  const values = Object.values(deviceData);
  const ctx = document.getElementById("chartDevice").getContext("2d");
  if(chartDevice) chartDevice.destroy();
  chartDevice = new Chart(ctx, {
    type: "doughnut",
    data: { labels, datasets:[{ data: values, backgroundColor:["#3f51b5","#009688","#ff5722","#9c27b0"] }]},
    options:{ responsive:true }
  });
}

function renderTrendChart(trendData){
  const labels = Object.keys(trendData);
  const values = Object.values(trendData);
  const ctx = document.getElementById("chartTrend").getContext("2d");
  if(chartTrend) chartTrend.destroy();
  chartTrend = new Chart(ctx, {
    type: "line",
    data: { labels, datasets:[{ label:"Access Count", data: values, borderColor:"#3e95cd", fill:false }]},
    options:{ responsive:true }
  });
}

// ---------- filters ----------
function applyCourseFilter(course){
  currentCourse = course || "__all";
  $("courseFilter").value = currentCourse;
  // fetch course-specific monthly trend
  if(course === "__all"){
    fetchJSON("/api/monthly_trends").then(d=> renderTrendChart(d.overall || {}));
  } else {
    fetchJSON("/api/monthly_trends").then(d=>{
      const pc = d.per_course_top5 || {};
      const data = pc[course] || {};
      if(Object.keys(data).length === 0){
        // fallback: rebuild trend by filtering raw
        fetchJSON("/api/raw").then(rows=>{
          const f = rows.filter(r => r.techno === course);
          const counts = {};
          f.forEach(r=>{
            const m = (r.accessdate || "").slice(0,7);
            if(m) counts[m] = (counts[m]||0) + 1;
          });
          renderTrendChart(counts);
        });
      } else renderTrendChart(data);
    });
  }

  // update charts/tables to show only that course: we will fetch per-course completion percentages and avg time
  if(course === "__all"){
    loadAll();
    return;
  }
  // fetch avg_time_per_course and show only the selected course bar highlighted
  fetchJSON("/api/avg_time_per_course").then(avg=>{
    // highlight single bar by re-rendering with single label
    const single = {};
    single[course] = avg[course] ?? 0;
    renderAvgTimeChart(single);
  });

  // completion percentages table show only selected row
  fetchJSON("/api/course_completion_percentages").then(cp=>{
    const tbody = document.querySelector("#completionTable tbody");
    tbody.innerHTML = "";
    if(cp[course]){
      const obj = cp[course];
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${course}</td><td>${obj.total}</td><td>${obj.completed}</td><td>${obj.completion_percent}%</td>`;
      tbody.appendChild(tr);
    }
  });

  // raw table show only those rows
  fetchJSON("/api/raw").then(rows=>{
    const filtered = rows.filter(r => r.techno === course).slice(0,200);
    populateRawTable(filtered);
  });
}

// ---------- UI wiring ----------
$("courseFilter").addEventListener("change",(e)=> applyCourseFilter(e.target.value));
$("clearFilter").addEventListener("click",()=>{ currentCourse="__all"; loadAll(); });
$("refreshData").addEventListener("click", async ()=>{
  await fetchJSON("/api/refresh");
  loadAll();
});

// initial load
loadAll();

// auto-refresh every 60s (optional)
setInterval(()=>{ loadAll(); }, 60000);
