(function () {
  "use strict";
  var tooltip = document.createElement("div");
  tooltip.className = "site-tooltip";
  tooltip.setAttribute("role", "status");
  tooltip.hidden = true;
  document.body.appendChild(tooltip);
  function show(target, text) {
    tooltip.textContent = text; tooltip.hidden = false;
    var box = target.getBoundingClientRect();
    tooltip.style.left = Math.max(8, Math.min(window.innerWidth - tooltip.offsetWidth - 8, box.left + box.width / 2 - tooltip.offsetWidth / 2)) + "px";
    tooltip.style.top = Math.max(8, box.top - tooltip.offsetHeight - 8) + "px";
  }
  function hide() { tooltip.hidden = true; }
  function initTooltips(root) {
    (root || document).querySelectorAll("[data-tooltip]").forEach(function (mark) {
      if (mark.dataset.tooltipReady) return;
      mark.dataset.tooltipReady = "1"; mark.tabIndex = mark.tabIndex >= 0 ? mark.tabIndex : 0;
      mark.setAttribute("aria-label", mark.dataset.tooltip);
      mark.addEventListener("mouseenter", function () { show(mark, mark.dataset.tooltip); });
      mark.addEventListener("mouseleave", hide);
      mark.addEventListener("focus", function () { show(mark, mark.dataset.tooltip); });
      mark.addEventListener("blur", hide);
      mark.addEventListener("click", function () { if (mark.dataset.pinned === "1") { mark.dataset.pinned = "0"; hide(); } else { mark.dataset.pinned = "1"; show(mark, mark.dataset.tooltip); } });
      mark.addEventListener("keydown", function (event) { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); mark.click(); } });
    });
  }
  initTooltips();

  document.querySelectorAll("[data-team-toggle]").forEach(function (toggle) {
    toggle.addEventListener("click", function () {
      var team = toggle.dataset.teamToggle;
      document.querySelectorAll("[data-team='" + team + "']").forEach(function (element) { element.classList.toggle("is-hidden"); });
      toggle.setAttribute("aria-pressed", toggle.getAttribute("aria-pressed") !== "true");
    });
  });
  function share(button, text) {
    var url = window.location.href;
    if (button === "whatsapp") window.open("https://wa.me/?text=" + encodeURIComponent(text), "_blank", "noopener");
    else if (button === "x") window.open("https://twitter.com/intent/tweet?text=" + encodeURIComponent(text), "_blank", "noopener");
    else if (button === "copy" && navigator.clipboard) navigator.clipboard.writeText(text);
    else if (button === "native" && navigator.share) navigator.share({ title: document.title, text: text, url: url });
    else if (button === "native") window.prompt("Copy this link", url);
  }
  document.querySelectorAll("[data-share]").forEach(function (button) {
    button.addEventListener("click", function () { share(button.dataset.share, (document.querySelector("[data-share-text]") || {}).textContent || document.title); });
  });
  document.querySelectorAll(".xg-race").forEach(function (chart) {
    var crosshair = chart.querySelector(".xg-crosshair"), readout = chart.parentElement.querySelector(".xg-readout");
    function move(event) {
      var point = event.touches ? event.touches[0] : event, rect = chart.getBoundingClientRect();
      if (!point) return;
      var minute = Math.max(0, Math.min(120, (point.clientX - rect.left) / rect.width * 120));
      crosshair.removeAttribute("hidden"); crosshair.setAttribute("x1", point.clientX - rect.left); crosshair.setAttribute("x2", point.clientX - rect.left);
      var series = Array.from(chart.querySelectorAll("[data-series]")).map(function (node) {
        var latest = node.dataset.series.split(" ").map(function (pair) { var bits = pair.split(":"); return { minute: +bits[0], xg: +bits[1] }; }).filter(function (v) { return v.minute <= minute; }).pop() || { xg: 0 };
        return (node.dataset.team === "home" ? "Home " : "Away ") + latest.xg.toFixed(2);
      });
      var eventAt = Array.from(chart.querySelectorAll("[data-minute]")).map(function (node) { return { minute: +node.dataset.minute, text: node.dataset.value || "" }; }).filter(function (v) { return v.minute <= minute; }).pop();
      readout.textContent = "Minute " + Math.round(minute) + " · " + series.join(" · ") + (eventAt ? " · " + eventAt.text : "");
    }
    chart.addEventListener("mousemove", move); chart.addEventListener("touchmove", move, { passive: true });
    chart.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      chart.dataset.keyboardMinute = String(Math.max(0, Math.min(120, +(chart.dataset.keyboardMinute || 0) + (event.key === "ArrowRight" ? 1 : -1))));
      move({ clientX: chart.getBoundingClientRect().left + chart.dataset.keyboardMinute / 120 * chart.getBoundingClientRect().width });
    });
  });

  var dataNode = document.getElementById("comparison-data");
  if (!dataNode) return;
  var data = JSON.parse(dataNode.textContent), table = document.querySelector("#expected-table tbody");
  var columns = data.table_columns;
  function numeric(value) { return typeof value === "number" ? value : (Number(value) || 0); }
  function renderTable(key, direction) {
    var rows = data.table.map(function (row, index) { return { row: row, index: index }; });
    rows.sort(function (a, b) { var av = a.row[key], bv = b.row[key]; if (typeof av === "number" || typeof bv === "number") return (numeric(av) - numeric(bv)) * direction || a.index - b.index; return String(av).localeCompare(String(bv)) * direction || a.index - b.index; });
    table.innerHTML = rows.map(function (entry, index) {
      var row = entry.row, delta = numeric(row["Pts-xPts"]);
      var label = delta > 0.2 ? "Over-performing" : delta < -0.2 ? "Under-performing" : "Tracking xPts";
      var team = data.teams[row.Team], crest = team && team.logo ? "<img class='table-crest' src='" + team.logo + "' alt='' loading='lazy'>" : "";
      return "<tr><td>" + (index + 1) + "</td><th scope='row'>" + crest + row.Team + "</th>" + columns.slice(2).map(function (column) { return "<td>" + row[column] + "</td>"; }).join("") + "<td class='actual-rank'>" + row.actual_rank + "</td><td class='performance-label'>" + label + "</td></tr>";
    }).join("");
  }
  renderTable("xPts", -1);
  document.querySelectorAll("#expected-table th[data-sort]").forEach(function (header) {
    header.addEventListener("click", function () {
      var key = header.dataset.sort, descending = header.getAttribute("aria-sort") !== "descending";
      document.querySelectorAll("#expected-table th[data-sort]").forEach(function (other) { other.setAttribute("aria-sort", "none"); other.querySelector(".sort-arrow").textContent = ""; });
      header.setAttribute("aria-sort", descending ? "descending" : "ascending"); header.querySelector(".sort-arrow").textContent = descending ? "↓" : "↑";
      renderTable(key, descending ? -1 : 1);
    });
    header.querySelector("button").addEventListener("keydown", function (event) { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); header.click(); } });
  });

  var selects = [document.getElementById("compare-a"), document.getElementById("compare-b")];
  var names = Object.keys(data.teams).sort(), bySlug = {};
  names.forEach(function (name) { bySlug[data.teams[name].slug] = name; selects.forEach(function (select) { var option = document.createElement("option"); option.value = data.teams[name].slug; option.textContent = name; select.appendChild(option); }); });
  var hash = new URLSearchParams(window.location.hash.slice(1)), latest = data.latest || {};
  selects[0].value = bySlug[hash.get("a")] ? hash.get("a") : (latest.home && data.teams[latest.home] ? data.teams[latest.home].slug : (names[0] ? data.teams[names[0]].slug : ""));
  selects[1].value = bySlug[hash.get("b")] ? hash.get("b") : (latest.away && data.teams[latest.away] ? data.teams[latest.away].slug : (names[1] ? data.teams[names[1]].slug : ""));
  function bar(label, left, right) { var total = Math.abs(left) + Math.abs(right) || 1; return "<div class='compare-bar' data-tooltip='" + label + ": " + left + " vs " + right + "'><span style='width:" + Math.abs(left) / total * 50 + "%'>" + left + "</span><i></i><span style='width:" + Math.abs(right) / total * 50 + "%'>" + right + "</span></div>"; }
  function renderComparison() {
    var a = bySlug[selects[0].value], b = bySlug[selects[1].value], left = data.teams[a], right = data.teams[b];
    if (!left || !right) { document.getElementById("comparison-content").innerHTML = "<p class='empty-state'>No clubs are available in this data snapshot yet.</p>"; return; }
    window.history.replaceState(null, "", "#a=" + left.slug + "&b=" + right.slug);
    document.getElementById("crest-preview").innerHTML = (left.logo ? "<img class='compare-crest' src='" + left.logo + "' alt=''>" : "") + left.name + "  ·  " + (right.logo ? "<img class='compare-crest' src='" + right.logo + "' alt=''>" : "") + right.name;
    var metrics = [["P", "matches"], ["W", "wins"], ["D", "draws"], ["L", "losses"], ["GF", "gf"], ["GA", "ga"], ["xGF", "xgf"], ["xGA", "xga"], ["xGD", "xgd"], ["Shots", "shots"], ["Possession", "possession"], ["Fouls", "fouls"], ["Yellows", "yellows"]];
    var html = "<h3>Season summary</h3>" + metrics.map(function (metric) { return "<div class='comparison-metric'><b>" + metric[0] + "</b>" + bar(metric[0], left[metric[1]], right[metric[1]]) + "</div>"; }).join("");
    function matchRows(team) { return data.matches.filter(function (match) { return match.home === team || match.away === team; }).slice(0, 20).map(function (match) { var isHome = match.home === team, opponent = isHome ? match.away : match.home, result = isHome ? match.home_result : match.away_result; return "<div class='match-row compact-row' data-tooltip='" + opponent + " · " + match.home_score + "-" + match.away_score + " · xG " + match.home_xg + "-" + match.away_xg + "'><b>" + result + "</b> " + opponent + " <span>xG " + (isHome ? match.home_xg : match.away_xg) + " for / " + (isHome ? match.away_xg : match.home_xg) + " against</span></div>"; }).join("") || "<p class='empty-state'>No matches for this club yet.</p>"; }
    var h2h = data.head_to_head[[a, b].sort().join("|")] || [];
    html += "<div class='comparison-columns'><div><h3>Match-by-match xG</h3>" + matchRows(a) + "</div><div><h3>Match-by-match xG</h3>" + matchRows(b) + "</div></div><h3>Last-5 form</h3><div class='form-strip'>" + left.form.concat(right.form).map(function (item) { return "<span data-tooltip='xG difference " + item.xgd + "'>" + item.result + "</span>"; }).join("") + "</div><h3>Head-to-head this season</h3>" + (h2h.length ? h2h.map(function (match) { return "<div class='compact-row'>" + match.home + " " + match.home_score + "-" + match.away_score + " " + match.away + " · xG " + match.home_xg + "-" + match.away_xg + "</div>"; }).join("") : "<p class='empty-state'>No head-to-head matches this season.</p>");
    function luck(team) { var small = team.matches < 5, goals = team.gf - team.xgf, points = team.points - team.xpoints, label = small ? "Small sample, don't start a war yet" : goals > 0 && points > 0 ? "Running hot" : "Due a correction"; return "<div class='luck'><h3>Luck index · " + team.name + "</h3>" + bar("Goals vs xG", goals.toFixed(2), 0) + bar("Points vs xPts", points.toFixed(2), 0) + "<p>" + label + "</p></div>"; }
    html += luck(left) + luck(right); document.getElementById("comparison-content").innerHTML = html; initTooltips(document.getElementById("comparison-content"));
    document.getElementById("comparison-share-text").textContent = left.name + " vs " + right.name + ". Expected table: " + left.name + " " + left.xpoints + " xPts, " + right.name + " " + right.xpoints + " xPts. Compare the receipts: " + window.location.href;
  }
  selects.forEach(function (select) { select.addEventListener("change", renderComparison); });
  document.querySelectorAll("[data-comparison-share]").forEach(function (button) { button.addEventListener("click", function () { share(button.dataset.comparisonShare, document.getElementById("comparison-share-text").textContent); }); });
  renderComparison();
})();
