document.addEventListener("DOMContentLoaded",()=>{
 if(typeof io!=="function")return; const socket=io();
 socket.on("order_status_changed",data=>{
  fetch("/api/my-orders").then(r=>r.json()).then(orders=>{
   const order=orders.find(o=>o.id===data.order_id);if(!order)return;
   const notice=document.createElement("div");notice.className="flash success";notice.textContent=`Order ${order.order_number} status: ${order.status}.`;document.querySelector("main.container")?.prepend(notice);
  }).catch(()=>{});
 });
});
