const entry = document.querySelector("#entry");
const feedback = document.querySelector("#feedback");
const result = document.querySelector("#result");

fetch("./recommendation.json")
  .then((response) => response.ok ? response.json() : Promise.reject())
  .then((dto) => {
    if (dto.source !== "SANDBOX_SYNTHETIC" || dto.fixture_only !== true || dto.external_effect !== false) throw new Error("untrusted dto");
    document.querySelector("#need-statement").textContent = `来自已确认的家庭需要：${dto.need_statement}`;
    document.querySelector("#audience-label").textContent = dto.audience_label;
    document.querySelector("#recommendation-reason").textContent = dto.recommendation_reason;
    document.querySelector("#plan-next-step").textContent = `动态方案下一步：${dto.next_step} 结束后，我们只会向你询问是否有帮助。`;
  })
  .catch(() => { document.querySelector("#need-statement").textContent = "推荐来源暂不可用，请返回直播首页。"; });

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
