document.addEventListener("DOMContentLoaded", () => {
  const script = document.querySelector("script[data-sales-live-url]");
  const endpoint = script ? script.dataset.salesLiveUrl : "";
  const dashboardSales = document.getElementById("dashboardSalesToday");
  const reportTotal = document.getElementById("reportTotal");
  if (!endpoint || (!dashboardSales && !reportTotal)) return;

  let currency = "KES";
  const money = (cents) => `${currency} ${(Number(cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = String(value);
  }

  function clear(element) {
    while (element.firstChild) element.removeChild(element.firstChild);
  }

  function titleCase(value) {
    return String(value || "").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function messageRow(tableBody, columns, message) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = columns;
    cell.textContent = message;
    row.appendChild(cell);
    tableBody.appendChild(row);
  }

  function renderStatusList(rows) {
    const list = document.getElementById("reportStatusList");
    if (!list) return;
    clear(list);
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No orders yet.";
      list.appendChild(empty);
      return;
    }
    rows.forEach(({ status, count }) => {
      const row = document.createElement("div");
      row.className = "list-row";
      const label = document.createElement("strong");
      label.textContent = titleCase(status);
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = String(count);
      row.append(label, badge);
      list.appendChild(row);
    });
  }

  function renderProducts(products) {
    const body = document.getElementById("reportProductRows");
    if (!body) return;
    clear(body);
    if (!products.length) {
      messageRow(body, 3, "No served products yet.");
      return;
    }
    products.forEach((product) => {
      const row = document.createElement("tr");
      [product.name, product.quantity, money(product.total_cents)].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = String(value);
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }

  function renderOrders(orders) {
    const body = document.getElementById("reportOrderRows");
    if (!body) return;
    clear(body);
    if (!orders.length) {
      messageRow(body, 6, "No served or completed orders yet.");
      return;
    }
    orders.forEach((order) => {
      const row = document.createElement("tr");
      const details = [
        order.order_number,
        order.customer,
        order.items.map((item) => `${item.name} × ${item.quantity}`).join(", "),
        order.date,
      ];
      details.forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = String(value);
        row.appendChild(cell);
      });
      const statusCell = document.createElement("td");
      const status = document.createElement("span");
      status.className = `status ${order.status}`;
      status.textContent = titleCase(order.status);
      statusCell.appendChild(status);
      row.appendChild(statusCell);
      const totalCell = document.createElement("td");
      totalCell.textContent = money(order.total_cents);
      row.appendChild(totalCell);
      body.appendChild(row);
    });
  }

  function render(data) {
    currency = data.currency || currency;
    if (dashboardSales && data.today) dashboardSales.textContent = money(data.today.total_cents);
    if (reportTotal && data.all_time) {
      reportTotal.textContent = money(data.all_time.total_cents);
      setText("reportOrderCount", data.all_time.order_count);
      setText("reportItemsServed", data.all_time.items_served);
    }
    renderStatusList(data.by_status || []);
    renderProducts(data.products || []);
    renderOrders(data.orders || []);
  }

  async function refresh() {
    try {
      const response = await fetch(endpoint, { cache: "no-store", headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) return;
      render(await response.json());
    } catch (error) {
      // Keep the last rendered totals if the connection drops.
    }
  }

  refresh();
  setInterval(() => {
    if (!document.hidden) refresh();
  }, 10000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
  window.addEventListener("sales:refresh", refresh);
});
