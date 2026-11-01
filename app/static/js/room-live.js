document.addEventListener("DOMContentLoaded",()=>{
 if(typeof io!=="function")return;const socket=io();
 socket.on("room_availability_changed",()=>{ /* Reload only room status labels on explicit refresh to avoid changing a user's chosen booking form. */ });
});
