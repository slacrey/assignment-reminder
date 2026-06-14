const state = {
  children: [],
  assignments: [],
  logs: [],
  isRefreshing: false,
};

const nodes = {};

document.addEventListener("DOMContentLoaded", () => {
  bindNodes();
  nodes.childForm.addEventListener("submit", createChild);
  nodes.assignmentForm.addEventListener("submit", createAssignment);
  nodes.childrenList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-child-id]");
    if (button) {
      deleteChild(Number(button.dataset.deleteChildId), button.dataset.childName || "");
    }
  });
  nodes.assignmentsList.addEventListener("click", (event) => {
    const cancelButton = event.target.closest("[data-cancel-id]");
    if (cancelButton) {
      cancelAssignment(Number(cancelButton.dataset.cancelId));
      return;
    }

    const deleteButton = event.target.closest("[data-delete-assignment-id]");
    if (deleteButton) {
      deleteAssignment(Number(deleteButton.dataset.deleteAssignmentId));
    }
  });
  nodes.reminderLogs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-log-id]");
    if (button) {
      deleteReminderLog(Number(button.dataset.deleteLogId));
    }
  });
  setDefaultReminderTime();
  refreshAll();
  setInterval(refreshAll, 3000);
});

function bindNodes() {
  nodes.childrenCount = document.getElementById("children-count");
  nodes.pendingCount = document.getElementById("pending-count");
  nodes.logsCount = document.getElementById("logs-count");
  nodes.lastUpdated = document.getElementById("last-updated");
  nodes.childrenStatus = document.getElementById("children-status");
  nodes.assignmentsStatus = document.getElementById("assignments-status");
  nodes.logsStatus = document.getElementById("logs-status");
  nodes.assignmentFormStatus = document.getElementById("assignment-form-status");
  nodes.childForm = document.getElementById("child-form");
  nodes.childName = document.getElementById("child-name");
  nodes.childQq = document.getElementById("child-qq");
  nodes.childFormMessage = document.getElementById("child-form-message");
  nodes.childrenList = document.getElementById("children-list");
  nodes.assignmentForm = document.getElementById("assignment-form");
  nodes.assignmentChild = document.getElementById("assignment-child");
  nodes.assignmentTitle = document.getElementById("assignment-title");
  nodes.assignmentDescription = document.getElementById("assignment-description");
  nodes.assignmentRemindAt = document.getElementById("assignment-remind-at");
  nodes.assignmentFormMessage = document.getElementById("assignment-form-message");
  nodes.assignmentsList = document.getElementById("assignments-list");
  nodes.reminderLogs = document.getElementById("reminder-logs");
}

async function loadChildren() {
  try {
    const children = await fetchJson("/api/children");
    state.children = children;
    renderChildren();
    renderChildOptions();
    setSectionStatus(nodes.childrenStatus, `已更新 ${shortTime()}`);
    updateSummary();
    return true;
  } catch (error) {
    setSectionStatus(nodes.childrenStatus, `读取失败：${error.message}`, "error");
    return false;
  }
}

async function loadAssignments() {
  try {
    const assignments = await fetchJson("/api/assignments");
    state.assignments = assignments;
    renderAssignments();
    setSectionStatus(nodes.assignmentsStatus, `已更新 ${shortTime()}`);
    updateSummary();
    return true;
  } catch (error) {
    setSectionStatus(nodes.assignmentsStatus, `读取失败：${error.message}`, "error");
    return false;
  }
}

async function loadReminderLogs() {
  try {
    const logs = await fetchJson("/api/reminder-logs");
    state.logs = logs;
    renderReminderLogs();
    setSectionStatus(nodes.logsStatus, `已更新 ${shortTime()}`);
    updateSummary();
    return true;
  } catch (error) {
    setSectionStatus(nodes.logsStatus, `读取失败：${error.message}`, "error");
    return false;
  }
}

async function createChild(event) {
  event.preventDefault();
  clearFormMessage(nodes.childFormMessage);
  clearInvalid(nodes.childName, nodes.childQq);

  const name = nodes.childName.value.trim();
  const qqNumber = nodes.childQq.value.trim();

  if (!name) {
    showFormMessage(nodes.childFormMessage, "请输入姓名。", "error");
    markInvalid(nodes.childName);
    nodes.childName.focus();
    return;
  }
  if (!/^[0-9]+$/.test(qqNumber)) {
    showFormMessage(nodes.childFormMessage, "QQ 只能填写数字。", "error");
    markInvalid(nodes.childQq);
    nodes.childQq.focus();
    return;
  }

  setFormBusy(nodes.childForm, true);
  try {
    await fetchJson("/api/children", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, qq_number: qqNumber }),
    });
    nodes.childForm.reset();
    clearInvalid(nodes.childName, nodes.childQq);
    showFormMessage(nodes.childFormMessage, "已添加孩子。", "success");
    await Promise.allSettled([loadChildren(), loadAssignments()]);
  } catch (error) {
    showFormMessage(nodes.childFormMessage, error.message, "error");
  } finally {
    setFormBusy(nodes.childForm, false);
  }
}

async function createAssignment(event) {
  event.preventDefault();
  clearFormMessage(nodes.assignmentFormMessage);
  clearInvalid(
    nodes.assignmentChild,
    nodes.assignmentTitle,
    nodes.assignmentRemindAt,
  );

  const childId = Number(nodes.assignmentChild.value);
  const title = nodes.assignmentTitle.value.trim();
  const description = nodes.assignmentDescription.value.trim();
  const remindAt = normalizeLocalDateTime(nodes.assignmentRemindAt.value);

  if (!childId) {
    showFormMessage(nodes.assignmentFormMessage, "请选择孩子。", "error");
    markInvalid(nodes.assignmentChild);
    nodes.assignmentChild.focus();
    return;
  }
  if (!title) {
    showFormMessage(nodes.assignmentFormMessage, "请输入作业标题。", "error");
    markInvalid(nodes.assignmentTitle);
    nodes.assignmentTitle.focus();
    return;
  }
  if (!remindAt) {
    showFormMessage(nodes.assignmentFormMessage, "请选择提醒时间。", "error");
    markInvalid(nodes.assignmentRemindAt);
    nodes.assignmentRemindAt.focus();
    return;
  }

  setFormBusy(nodes.assignmentForm, true);
  try {
    await fetchJson("/api/assignments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        child_id: childId,
        title,
        description,
        remind_at: remindAt,
      }),
    });
    nodes.assignmentTitle.value = "";
    nodes.assignmentDescription.value = "";
    setDefaultReminderTime();
    clearInvalid(nodes.assignmentChild, nodes.assignmentTitle, nodes.assignmentRemindAt);
    showFormMessage(nodes.assignmentFormMessage, "已添加作业。", "success");
    await Promise.allSettled([loadAssignments(), loadChildren()]);
  } catch (error) {
    showFormMessage(nodes.assignmentFormMessage, error.message, "error");
  } finally {
    setFormBusy(nodes.assignmentForm, false);
  }
}

async function cancelAssignment(id) {
  const button = document.querySelector(`[data-cancel-id="${id}"]`);
  if (button) {
    button.disabled = true;
    button.textContent = "取消中";
  }

  try {
    await fetchJson(`/api/assignments/${id}/cancel`, { method: "PATCH" });
    await Promise.allSettled([loadAssignments(), loadReminderLogs(), loadChildren()]);
  } catch (error) {
    setSectionStatus(nodes.assignmentsStatus, `取消失败：${error.message}`, "error");
    if (button) {
      button.disabled = false;
      button.textContent = "取消";
    }
  }
}

async function deleteAssignment(id) {
  if (!window.confirm("删除这个作业？相关提醒日志也会一起删除。")) {
    return;
  }

  const button = document.querySelector(`[data-delete-assignment-id="${id}"]`);
  if (button) {
    button.disabled = true;
    button.textContent = "删除中";
  }

  try {
    await fetchJson(`/api/assignments/${id}`, { method: "DELETE" });
    await refreshAll();
  } catch (error) {
    setSectionStatus(nodes.assignmentsStatus, `删除失败：${error.message}`, "error");
    if (button) {
      button.disabled = false;
      button.textContent = "删除";
    }
  }
}

async function deleteChild(id, name) {
  const label = name ? `“${name}”` : "这个孩子";
  if (!window.confirm(`删除${label}？相关作业和提醒日志也会一起删除。`)) {
    return;
  }

  const button = document.querySelector(`[data-delete-child-id="${id}"]`);
  if (button) {
    button.disabled = true;
    button.textContent = "删除中";
  }

  try {
    await fetchJson(`/api/children/${id}`, { method: "DELETE" });
    await refreshAll();
  } catch (error) {
    setSectionStatus(nodes.childrenStatus, `删除失败：${error.message}`, "error");
    if (button) {
      button.disabled = false;
      button.textContent = "删除";
    }
  }
}

async function deleteReminderLog(id) {
  if (!window.confirm("删除这条提醒记录？")) {
    return;
  }

  const button = document.querySelector(`[data-delete-log-id="${id}"]`);
  if (button) {
    button.disabled = true;
    button.textContent = "删除中";
  }

  try {
    await fetchJson(`/api/reminder-logs/${id}`, { method: "DELETE" });
    await Promise.allSettled([loadReminderLogs(), loadChildren()]);
  } catch (error) {
    setSectionStatus(nodes.logsStatus, `删除失败：${error.message}`, "error");
    if (button) {
      button.disabled = false;
      button.textContent = "删除";
    }
  }
}

async function refreshAll() {
  if (state.isRefreshing) {
    return;
  }
  state.isRefreshing = true;
  try {
    const results = await Promise.allSettled([
      loadChildren(),
      loadAssignments(),
      loadReminderLogs(),
    ]);
    const ok = results.every((result) => result.status === "fulfilled" && result.value);
    nodes.lastUpdated.textContent = ok ? shortTime() : "部分失败";
  } finally {
    state.isRefreshing = false;
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  });

  let payload = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  }

  if (!response.ok) {
    throw new Error(apiErrorMessage(payload, response.status));
  }

  return payload;
}

function renderChildren() {
  if (state.children.length === 0) {
    nodes.childrenList.innerHTML = emptyRow("暂无孩子", 5);
    return;
  }

  nodes.childrenList.innerHTML = state.children.map((child) => `
    <tr>
      <td><span class="cell-main">${escapeHtml(child.name)}</span></td>
      <td class="nowrap">${escapeHtml(child.qq_number)}</td>
      <td>${child.assignment_count}</td>
      <td class="cell-muted">${formatDate(child.last_reminded_at)}</td>
      <td>
        <button
          class="ghost-button"
          type="button"
          data-delete-child-id="${child.id}"
          data-child-name="${escapeHtml(child.name)}"
        >删除</button>
      </td>
    </tr>
  `).join("");
}

function renderChildOptions() {
  const selected = nodes.assignmentChild.value;

  if (state.children.length === 0) {
    nodes.assignmentChild.innerHTML = '<option value="">先添加孩子</option>';
    nodes.assignmentChild.disabled = true;
    nodes.assignmentFormStatus.textContent = "等待孩子";
    return;
  }

  nodes.assignmentChild.disabled = false;
  nodes.assignmentChild.innerHTML = [
    '<option value="">选择孩子</option>',
    ...state.children.map((child) => (
      `<option value="${child.id}">${escapeHtml(child.name)} · QQ ${escapeHtml(child.qq_number)}</option>`
    )),
  ].join("");

  if (selected && state.children.some((child) => String(child.id) === selected)) {
    nodes.assignmentChild.value = selected;
  }
  nodes.assignmentFormStatus.textContent = "";
}

function renderAssignments() {
  if (state.assignments.length === 0) {
    nodes.assignmentsList.innerHTML = emptyRow("暂无作业", 6);
    return;
  }

  nodes.assignmentsList.innerHTML = state.assignments.map((assignment) => {
    const canCancel = assignment.status === "pending";
    const cancelAction = canCancel
      ? `<button class="ghost-button" type="button" data-cancel-id="${assignment.id}">取消</button>`
      : "";
    const action = `
      <div class="action-group">
        ${cancelAction}
        <button
          class="ghost-button"
          type="button"
          data-delete-assignment-id="${assignment.id}"
        >删除</button>
      </div>
    `;

    return `
      <tr>
        <td>
          <span class="cell-main">${escapeHtml(assignment.child_name)}</span>
          <span class="cell-muted">QQ ${escapeHtml(assignment.child_qq_number)}</span>
        </td>
        <td><span class="cell-main">${escapeHtml(assignment.title)}</span></td>
        <td class="cell-muted">${escapeHtml(assignment.description || "--")}</td>
        <td class="nowrap">${formatDate(assignment.remind_at)}</td>
        <td>${statusBadge(assignment.status)}</td>
        <td>${action}</td>
      </tr>
    `;
  }).join("");
}

function renderReminderLogs() {
  if (state.logs.length === 0) {
    nodes.reminderLogs.innerHTML = emptyRow("暂无日志", 8);
    return;
  }

  nodes.reminderLogs.innerHTML = state.logs.map((log) => `
    <tr>
      <td class="nowrap">${formatDate(log.sent_at)}</td>
      <td>${escapeHtml(log.child_name)}</td>
      <td class="nowrap">${escapeHtml(log.target_qq)}</td>
      <td>${escapeHtml(log.assignment_title)}</td>
      <td>${statusBadge(log.status)}</td>
      <td class="cell-muted">
        ${escapeHtml(log.provider || "--")}
        ${log.provider_message_id ? `<span class="cell-muted">#${escapeHtml(log.provider_message_id)}</span>` : ""}
      </td>
      <td class="message-cell">${escapeHtml(log.error_message || log.message)}</td>
      <td>
        <button
          class="ghost-button"
          type="button"
          data-delete-log-id="${log.id}"
        >删除</button>
      </td>
    </tr>
  `).join("");
}

function updateSummary() {
  nodes.childrenCount.textContent = state.children.length;
  nodes.pendingCount.textContent = state.assignments.filter((item) => item.status === "pending").length;
  nodes.logsCount.textContent = state.logs.length;
}

function statusBadge(status) {
  const labels = {
    pending: "待提醒",
    reminded: "已提醒",
    cancelled: "已取消",
    success: "成功",
    failed: "失败",
  };
  const safeStatus = escapeHtml(status);
  return `<span class="status-badge status-${safeStatus}">${labels[status] || safeStatus}</span>`;
}

function setDefaultReminderTime() {
  const now = new Date();
  now.setMinutes(now.getMinutes() + 2);
  now.setSeconds(0, 0);
  const value = toLocalInputValue(now);
  nodes.assignmentRemindAt.min = value;
  nodes.assignmentRemindAt.value = value;
}

function normalizeLocalDateTime(value) {
  if (!value) {
    return "";
  }
  return value.length === 16 ? `${value}:00` : value;
}

function toLocalInputValue(date) {
  const pad = (number) => String(number).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join("-") + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatDate(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function shortTime() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());
}

function setSectionStatus(node, message, tone = "") {
  node.textContent = message;
  node.classList.toggle("error", tone === "error");
}

function showFormMessage(node, message, tone) {
  node.hidden = false;
  node.textContent = message;
  node.className = `form-message ${tone}`;
}

function clearFormMessage(node) {
  node.hidden = true;
  node.textContent = "";
  node.className = "form-message";
}

function setFormBusy(form, busy) {
  form.querySelectorAll("button, input, select, textarea").forEach((control) => {
    control.disabled = busy;
  });
}

function markInvalid(control) {
  control.setAttribute("aria-invalid", "true");
}

function clearInvalid(...controls) {
  controls.forEach((control) => control.removeAttribute("aria-invalid"));
}

function apiErrorMessage(payload, status) {
  if (payload && Array.isArray(payload.detail)) {
    const message = payload.detail
      .map((item) => item.msg || item.message)
      .filter(Boolean)
      .join("；");
    if (message) {
      return message;
    }
  }
  if (payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  return `请求失败（${status}）`;
}

function emptyRow(message, colspan) {
  return `<tr class="empty-row"><td colspan="${colspan}">${message}</td></tr>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
