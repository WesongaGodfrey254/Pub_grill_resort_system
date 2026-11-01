document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("menuToggle");
  toggle?.addEventListener("click", () => document.getElementById("mainNav")?.classList.toggle("open"));
  const getCart = () => { try { return JSON.parse(localStorage.getItem("pubGrillCart") || "[]"); } catch { return []; } };
  const count = getCart().reduce((sum, item) => sum + item.quantity, 0);
  ["cartCount", "cartCountBottom"].forEach(id => { const el=document.getElementById(id); if(el) el.textContent=count; });
  document.querySelectorAll(".add-cart").forEach(button => button.addEventListener("click", () => {
    const cart = getCart(); const id = Number(button.dataset.id);
    const existing = cart.find(item => item.product_id === id);
    if(existing) existing.quantity += 1;
    else cart.push({product_id:id, name:button.dataset.name, price:Number(button.dataset.price), quantity:1});
    localStorage.setItem("pubGrillCart", JSON.stringify(cart));
    const n=cart.reduce((sum,item)=>sum+item.quantity,0);
    ["cartCount","cartCountBottom"].forEach(key=>{const el=document.getElementById(key);if(el)el.textContent=n;});
    button.textContent="Added ✓"; setTimeout(()=>button.textContent="Add to cart",1000);
  }));
});
