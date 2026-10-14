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
      function highlight(active) {
        var event = mark.closest && mark.closest(".goal-event");
        if (event) event.classList.toggle("is-highlighted", active);
      }
      mark.addEventListener("mouseenter", function () { highlight(true); show(mark, mark.dataset.tooltip); });
      mark.addEventListener("mouseleave", function () { highlight(false); hide(); });
      mark.addEventListener("focus", function () { highlight(true); show(mark, mark.dataset.tooltip); });
      mark.addEventListener("blur", function () { highlight(false); hide(); });
      mark.addEventListener("click", function () { if (mark.dataset.pinned === "1") { mark.dataset.pinned = "0"; highlight(false); hide(); } else { mark.dataset.pinned = "1"; highlight(true); show(mark, mark.dataset.tooltip); } });
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
      var duration = +(chart.dataset.maxMinute || 90);
      var minute = Math.max(0, Math.min(duration, (point.clientX - rect.left) / rect.width * duration));
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
      var duration = +(chart.dataset.maxMinute || 90);
      chart.dataset.keyboardMinute = String(Math.max(0, Math.min(duration, +(chart.dataset.keyboardMinute || 0) + (event.key === "ArrowRight" ? 1 : -1))));
      move({ clientX: chart.getBoundingClientRect().left + chart.dataset.keyboardMinute / duration * chart.getBoundingClientRect().width });
    });
  });

  var dataNode = document.getElementById("comparison-data");
  if (!dataNode) return;
  var data = JSON.parse(dataNode.textContent), table = document.querySelector("#expected-table tbody");
  var columns = data.table_columns;
  function numeric(value) { return typeof value === "number" ? value : (Number(value) || 0); }
  function formatValue(column, value) {
    if (["P", "Pts", "GF", "GA", "GD"].indexOf(column) !== -1) return String(Math.round(numeric(value)));
    if (["xPts", "Pts-xPts", "xGF", "xGA", "xGD"].indexOf(column) !== -1) return numeric(value).toFixed(2);
    return String(value);
  }
  function formatMetric(key, value) {
    return ["matches", "wins", "draws", "losses", "gf", "ga", "shots", "fouls", "yellows"].indexOf(key) !== -1
      ? String(Math.round(numeric(value))) : numeric(value).toFixed(2);
  }
  function renderTable(key, direction) {
    var rows = data.table.map(function (row, index) { return { row: row, index: index }; });
    rows.sort(function (a, b) {
      var aUnplayed = numeric(a.row.P) === 0, bUnplayed = numeric(b.row.P) === 0;
      if (aUnplayed !== bUnplayed) return aUnplayed ? 1 : -1;
      var av = a.row[key], bv = b.row[key];
      if (typeof av === "number" || typeof bv === "number") return (numeric(av) - numeric(bv)) * direction || a.index - b.index;
      return String(av).localeCompare(String(bv)) * direction || a.index - b.index;
    });
    table.innerHTML = rows.map(function (entry, index) {
      var row = entry.row, delta = numeric(row["Pts-xPts"]);
      var matches = numeric(row.P);
      var label = matches === 0 ? "Yet to play" : matches < 3 ? "Early days" : delta > 0.2 ? "Over-performing" : delta < -0.2 ? "Under-performing" : "Tracking xPts";
      var team = data.teams[row.Team], crest = team && team.logo ? "<img class='table-crest' src='" + team.logo + "' alt='' loading='lazy'>" : "";
      return "<tr><td>" + (index + 1) + "</td><th scope='row'>" + crest + row.Team + "</th>" + columns.slice(2).map(function (column) { return "<td>" + formatValue(column, row[column]) + "</td>"; }).join("") + "<td class='actual-rank'>" + row.actual_rank + "</td><td class='performance-label'>" + label + "</td></tr>";
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
  function twoSidedBar(label, left, right, leftTeam, rightTeam) {
    var leftValue = numeric(left), rightValue = numeric(right), total = Math.abs(leftValue) + Math.abs(rightValue);
    var leftShare = total ? Math.abs(leftValue) / total : 0.5, rightShare = total ? Math.abs(rightValue) / total : 0.5;
    var leftText = formatMetric("", leftValue), rightText = formatMetric("", rightValue);
    var tooltip = label + ": " + leftText + " (" + (leftShare * 100).toFixed(2) + "%) vs " + rightText + " (" + (rightShare * 100).toFixed(2) + "%)";
    return "<div class='comparison-metric' data-tooltip='" + tooltip + "'><div class='comparison-metric-label'>" + label + "</div><div class='compare-track' style='--bar-a-color:" + leftTeam.color + ";--bar-a-on:" + leftTeam.on_color + ";--bar-b-color:" + rightTeam.color + ";--bar-b-on:" + rightTeam.on_color + "'><span class='compare-segment compare-a' style='width:" + (leftShare * 100) + "%'><b>" + leftText + "</b></span><span class='compare-segment compare-b' style='width:" + (rightShare * 100) + "%'><b>" + rightText + "</b></span></div><div class='compare-values'><span>" + leftText + "</span><span>" + rightText + "</span></div></div>";
  }
  function renderComparison() {
    var a = bySlug[selects[0].value], b = bySlug[selects[1].value], left = data.teams[a], right = data.teams[b];
    if (!left || !right) { document.getElementById("comparison-content").innerHTML = "<p class='empty-state'>No clubs are available in this data snapshot yet.</p>"; return; }
    window.history.replaceState(null, "", "#a=" + left.slug + "&b=" + right.slug);
    document.getElementById("crest-preview").innerHTML = (left.logo ? "<img class='compare-crest' src='" + left.logo + "' alt=''>" : "") + left.name + "  ·  " + (right.logo ? "<img class='compare-crest' src='" + right.logo + "' alt=''>" : "") + right.name;
    var metrics = [["P", "matches"], ["W", "wins"], ["D", "draws"], ["L", "losses"], ["GF", "gf"], ["GA", "ga"], ["xGF", "xgf"], ["xGA", "xga"], ["xGD", "xgd"], ["Shots", "shots"], ["Possession", "possession"], ["Fouls", "fouls"], ["Yellows", "yellows"]];
    var html = "<h3>Season summary</h3><div class='comparison-summary'>" + metrics.map(function (metric) { return twoSidedBar(metric[0], left[metric[1]], right[metric[1]], left, right); }).join("") + "</div>";
    function matchRows(team) {
      var matches = data.matches.filter(function (match) { return match.home === team || match.away === team; }).slice(0, 20);
      var maximum = Math.max.apply(null, matches.reduce(function (values, match) { return values.concat([numeric(match.home_xg), numeric(match.away_xg)]); }, []).concat([1]));
      return matches.map(function (match) {
        var isHome = match.home === team, opponent = isHome ? match.away : match.home, opponentData = data.teams[opponent];
        var result = isHome ? match.home_result : match.away_result, forXg = numeric(isHome ? match.home_xg : match.away_xg), againstXg = numeric(isHome ? match.away_xg : match.home_xg);
        var forText = forXg.toFixed(2), againstText = againstXg.toFixed(2), crest = opponentData && opponentData.logo ? "<img class='opponent-crest' src='" + opponentData.logo + "' alt=''>" : "";
        return "<div class='comparison-match' data-tooltip='" + opponent + " · " + match.home_score + "-" + match.away_score + "'><div class='match-opponent'><b class='result-chip result-" + result.toLowerCase() + "'>" + result + "</b>" + crest + "<strong>" + opponent + "</strong></div><div class='xg-bars'><span class='xg-label'>xG for <b>" + forText + "</b></span><i><em style='width:" + (forXg / maximum * 100) + "%;background:" + data.teams[team].color + "'></em></i><span class='xg-label'>xG against <b>" + againstText + "</b></span><i><em style='width:" + (againstXg / maximum * 100) + "%;background:" + data.teams[opponent].color + "'></em></i></div></div>";
      }).join("") || "<p class='empty-state'>No matches for this club yet.</p>";
    }
    var h2h = data.head_to_head[[a, b].sort().join("|")] || [];
    html += "<div class='comparison-columns'><div><h3>Match-by-match xG</h3>" + matchRows(a) + "</div><div><h3>Match-by-match xG</h3>" + matchRows(b) + "</div></div><h3>Last-5 form</h3><div class='form-strip'>" + left.form.concat(right.form).map(function (item) { return "<span data-tooltip='xG difference " + item.xgd.toFixed(2) + "'>" + item.result + "</span>"; }).join("") + "</div><h3>Head-to-head this season</h3>" + (h2h.length ? h2h.map(function (match) { return "<div class='compact-row'>" + match.home + " " + match.home_score + "-" + match.away_score + " " + match.away + " · xG " + match.home_xg.toFixed(2) + "-" + match.away_xg.toFixed(2) + "</div>"; }).join("") : "<p class='empty-state'>No head-to-head matches this season.</p>");
    function luck(team, example) {
      var goals = team.gf - team.xgf, points = team.points - team.xpoints, small = team.matches < 5;
      var label = small ? "Small sample" : goals >= 0.5 && points >= 0.5 ? "Running hot" : goals <= -0.5 && points <= -0.5 ? "Due a correction" : "Mixed signals";
      function luckBar(label, value, suffix) {
        var width = Math.min(50, Math.abs(value) / (Math.max(1, Math.abs(value)) + 1) * 50);
        return "<div class='luck-bar'><span>" + label + "</span><i><em class='" + (value >= 0 ? "positive" : "negative") + "' style='width:" + width.toFixed(1) + "%'></em></i><b>" + (value >= 0 ? "+" : "") + value.toFixed(2) + suffix + "</b></div>";
      }
      var info = "<details class='luck-info'><summary class='info-button' aria-label='About the luck index'>i</summary><p>Luck index compares what happened with what the chances expected: it is not a verdict on quality.</p><p>Read the diverging bars from the centre: right means results ran ahead of the chances; left means they fell behind.</p><p>Formulas: goals − xG and points − xPts. Labels use ±0.50 goals and ±0.50 points; otherwise the signal is mixed. With fewer than 5 matches, we show “Small sample” rather than a strong label.</p><p>" + (example ? "Worked example from this data: " + example.name + " has " + example.gf + " goals against " + example.xgf.toFixed(2) + " xG (" + (example.gf - example.xgf >= 0 ? "+" : "") + (example.gf - example.xgf).toFixed(2) + ") and " + example.points + " points against " + example.xpoints.toFixed(2) + " xPts (" + (example.points - example.xpoints >= 0 ? "+" : "") + (example.points - example.xpoints).toFixed(2) + ")." : "No played matches are available for a worked example.") + "</p><p>xG (expected goals) is the estimated number of goals a team’s chances would produce on average.</p></details>";
      return "<div class='luck'><div class='luck-heading'><h3>Luck index · " + team.name + "</h3>" + info + "</div><p><strong>" + label + "</strong></p><div class='luck-bars'>" + luckBar("Goals − xG", goals, "") + luckBar("Points − xPts", points, "") + "</div><div class='luck-ends'><span>&lt;- unlucky</span><span>lucky -&gt;</span></div></div>";
    }
    var example = data.table.map(function (row) { return data.teams[row.Team]; }).filter(function (team) { return team && team.matches > 0; }).sort(function (x, y) { return (y.points - y.xpoints) - (x.points - x.xpoints); })[0];
    html += luck(left, example) + luck(right, example); document.getElementById("comparison-content").innerHTML = html; initTooltips(document.getElementById("comparison-content"));
    document.getElementById("comparison-share-text").textContent = left.name + " vs " + right.name + ". Expected table: " + left.name + " " + formatMetric("xpoints", left.xpoints) + " xPts, " + right.name + " " + formatMetric("xpoints", right.xpoints) + " xPts. Compare the receipts: " + window.location.href;
  }
  selects.forEach(function (select) { select.addEventListener("change", renderComparison); });
  document.querySelectorAll("[data-comparison-share]").forEach(function (button) { button.addEventListener("click", function () { share(button.dataset.comparisonShare, document.getElementById("comparison-share-text").textContent); }); });
  renderComparison();
})();
