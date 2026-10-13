(function () {
  "use strict";
  var tooltip = document.createElement("div");
  tooltip.className = "site-tooltip";
  tooltip.setAttribute("role", "status");
  tooltip.hidden = true;
  document.body.appendChild(tooltip);
  function show(target, text) {
    tooltip.textContent = text;
    tooltip.hidden = false;
    var box = target.getBoundingClientRect();
    tooltip.style.left = Math.max(8, Math.min(window.innerWidth - tooltip.offsetWidth - 8, box.left + box.width / 2 - tooltip.offsetWidth / 2)) + "px";
    tooltip.style.top = Math.max(8, box.top - tooltip.offsetHeight - 8) + "px";
  }
  function hide() { tooltip.hidden = true; }
  document.querySelectorAll("[data-tooltip]").forEach(function (mark) {
    mark.tabIndex = mark.tabIndex >= 0 ? mark.tabIndex : 0;
    mark.setAttribute("aria-label", mark.getAttribute("data-tooltip"));
    mark.addEventListener("mouseenter", function () { show(mark, mark.dataset.tooltip); });
    mark.addEventListener("mouseleave", hide);
    mark.addEventListener("focus", function () { show(mark, mark.dataset.tooltip); });
    mark.addEventListener("blur", hide);
    mark.addEventListener("click", function () {
      if (mark.dataset.pinned === "1") { mark.dataset.pinned = "0"; hide(); }
      else { mark.dataset.pinned = "1"; show(mark, mark.dataset.tooltip); }
    });
    mark.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); mark.click(); }
    });
  });
  document.querySelectorAll("[data-team-toggle]").forEach(function (toggle) {
    toggle.addEventListener("click", function () {
      var team = toggle.dataset.teamToggle;
      document.querySelectorAll("[data-team='" + team + "']").forEach(function (element) {
        element.classList.toggle("is-hidden");
      });
      document.querySelectorAll("[data-share]").forEach(function (button) {
        button.addEventListener("click", function () {
          var text = (document.querySelector("[data-share-text]") || {}).textContent || document.title;
          var url = window.location.href;
          if (button.dataset.share === "whatsapp") window.open("https://wa.me/?text=" + encodeURIComponent(text), "_blank", "noopener");
          else if (button.dataset.share === "x") window.open("https://twitter.com/intent/tweet?text=" + encodeURIComponent(text), "_blank", "noopener");
          else if (button.dataset.share === "copy" && navigator.clipboard) navigator.clipboard.writeText(text);
          else if (button.dataset.share === "native" && navigator.share) navigator.share({ title: document.title, text: text, url: url });
          else if (button.dataset.share === "native") window.prompt("Copy this link", url);
        });
      });
      toggle.setAttribute("aria-pressed", toggle.getAttribute("aria-pressed") !== "true");
    });
  });
  document.querySelectorAll(".xg-race").forEach(function (chart) {
    var crosshair = chart.querySelector(".xg-crosshair");
    var readout = chart.parentElement.querySelector(".xg-readout");
    function move(event) {
      var point = event.touches ? event.touches[0] : event;
      if (!point) return;
      var rect = chart.getBoundingClientRect();
      var minute = Math.max(0, Math.min(120, (point.clientX - rect.left) / rect.width * 120));
      crosshair.hidden = false;
      crosshair.setAttribute("x1", point.clientX - rect.left);
      crosshair.setAttribute("x2", point.clientX - rect.left);
      var series = Array.from(chart.querySelectorAll("[data-series]")).map(function (node) {
        var latest = node.dataset.series.split(" ").map(function (pair) {
          var bits = pair.split(":");
          return { minute: parseFloat(bits[0]), xg: parseFloat(bits[1]) };
        }).filter(function (value) { return value.minute <= minute; }).pop() || { xg: 0 };
        return (node.dataset.team === "home" ? "Home " : "Away ") + latest.xg.toFixed(2);
      });
      var events = Array.from(chart.querySelectorAll("[data-minute]")).map(function (node) {
        return { minute: parseFloat(node.dataset.minute), text: node.dataset.value || "" };
      }).filter(function (value) { return value.minute <= minute; }).pop();
      readout.textContent = "Minute " + Math.round(minute) + " · " + series.join(" · ") + (events ? " · " + events.text : "");
    }
    chart.addEventListener("mousemove", move);
    chart.addEventListener("touchmove", move, { passive: true });
    chart.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      chart.dataset.keyboardMinute = String(Math.max(0, Math.min(120, Number(chart.dataset.keyboardMinute || 0) + (event.key === "ArrowRight" ? 1 : -1))));
      move({ clientX: chart.getBoundingClientRect().left + chart.dataset.keyboardMinute / 120 * chart.getBoundingClientRect().width });
    });
  });
})();
