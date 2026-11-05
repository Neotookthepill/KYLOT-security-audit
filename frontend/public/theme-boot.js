(function () {
  try {
    var t = localStorage.getItem("qylot-theme") === "dark" ? "dark" : "light";
    document.documentElement.classList.toggle("dark", t === "dark");
    document.documentElement.dataset.theme = t;
    document.documentElement.style.colorScheme = t;
  } catch (e) {}
})();
