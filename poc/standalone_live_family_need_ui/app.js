const entry = document.querySelector("#entry");
const feedback = document.querySelector("#feedback");
const result = document.querySelector("#result");

document.querySelector("#enter").addEventListener("click", () => {
  entry.classList.remove("hidden");
  entry.scrollIntoView({ behavior: "smooth", block: "center" });
});

document.querySelector("#complete").addEventListener("click", () => {
  feedback.classList.remove("hidden");
  feedback.scrollIntoView({ behavior: "smooth", block: "center" });
});

document.querySelectorAll("[data-answer]").forEach((button) => {
  button.addEventListener("click", () => {
    result.textContent = `已记录“${button.dataset.answer}”的合成回执；正式环境需经 ServiceFeedback port 与家长确认。`;
  });
});
