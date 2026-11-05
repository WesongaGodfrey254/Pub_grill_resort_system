document.addEventListener("DOMContentLoaded",()=>{
 if(typeof io!=="function")return;
 const socket=io();
 socket.on("order_created",data=>{
  if(!document.getElementById("adminOrderRows")){const n=document.createElement("div");n.className="flash success";n.textContent=`New order ${data.order_number} from ${data.customer} — KES ${Number(data.total).toFixed(2)}. Refresh orders to view details.`;document.querySelector("main.container")?.prepend(n);}
  else {const n=document.createElement("div");n.className="flash success";n.textContent=`New order ${data.order_number} from ${data.customer} received. Reload the order list to update details.`;document.querySelector("main.container")?.prepend(n);}
  if("Notification" in window && Notification.permission==="granted")new Notification("New order",{body:`${data.order_number} · ${data.customer}`});
  window.dispatchEvent(new CustomEvent("sales:refresh"));
 });
 socket.on("order_updated",data=>{const n=document.createElement("div");n.className="flash success";n.textContent=`${data.order_number} is now ${data.status}.`;document.querySelector("main.container")?.prepend(n);window.dispatchEvent(new CustomEvent("sales:refresh"));});
});
