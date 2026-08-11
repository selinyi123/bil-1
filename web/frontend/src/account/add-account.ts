import { sidebarLoginBtn } from "../dom";
import { renderAccountPool } from "../extra/index";
import { startJob } from "../jobs/index";
import { showToast } from "../shell/toast";

let settleTimer: number | null = null;

function syncAddAccountButton(button: HTMLButtonElement): void {
  // sidebar-login 仅在未登录时显示；复用其真实渲染状态，避免再维护一份 auth 状态。
  const loggedIn = Boolean(sidebarLoginBtn?.hidden);
  button.hidden = !loggedIn;
  button.disabled = document.body.classList.contains("job-running");
}

function refreshPoolAfterLoginSettles(): void {
  if (settleTimer) window.clearInterval(settleTimer);
  let ticks = 0;
  settleTimer = window.setInterval(() => {
    ticks += 1;
    if (document.body.classList.contains("job-running") && ticks < 240) return;
    if (settleTimer) {
      window.clearInterval(settleTimer);
      settleTimer = null;
    }
    renderAccountPool().catch(() => {});
  }, 1000);
}

/**
 * 已登录后显式提供“添加账号”，不再要求用户通过“退出登录 → 再扫码”猜测账号池行为。
 * 新账号仍复用现有 login Job；扫码完成后刷新账号池即可显示并切换。
 */
export function bindAddAccount(): void {
  const actions = document.querySelector<HTMLElement>(".sidebar-account-actions");
  if (!actions || document.getElementById("sidebar-add-account")) return;

  const button = document.createElement("button");
  button.type = "button";
  button.id = "sidebar-add-account";
  button.className = "btn btn-secondary btn-compact btn-block";
  button.textContent = "添加账号";
  button.title = "扫码添加另一个 B 站账号到本机账号池";
  actions.appendChild(button);
  syncAddAccountButton(button);

  // 登录状态和任务锁会改变现有按钮的 hidden/disabled/class；观察这些变化同步入口状态。
  const observer = new MutationObserver(() => syncAddAccountButton(button));
  if (sidebarLoginBtn) {
    observer.observe(sidebarLoginBtn, { attributes: true, attributeFilter: ["hidden"] });
  }
  observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });

  button.addEventListener("click", async () => {
    if (document.body.classList.contains("job-running")) {
      showToast("有任务正在运行", "info", "请等待当前任务结束后再添加账号");
      return;
    }
    button.disabled = true;
    try {
      await startJob("login", {});
      refreshPoolAfterLoginSettles();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      showToast(message || "添加账号失败", "error");
      syncAddAccountButton(button);
    }
  });
}
