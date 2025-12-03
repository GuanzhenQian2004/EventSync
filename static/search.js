document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("userSearch");
  const items = document.querySelectorAll(".event-item");

  if (!searchInput || !items.length) return;

  searchInput.addEventListener("input", () => {
    const q = searchInput.value.toLowerCase().trim();

    items.forEach(li => {
      const text = (li.dataset.search || "").toLowerCase();
      li.style.display = text.includes(q) ? "" : "none";
    });
  });
});
