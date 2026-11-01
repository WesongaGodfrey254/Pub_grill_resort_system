document.addEventListener("DOMContentLoaded", () => {
 const itemsEl=document.getElementById("cartItems"), emptyEl=document.getElementById("cartEmpty"), checkout=document.getElementById("cartCheckout");
 const totalEl=document.getElementById("cartTotal"), place=document.getElementById("placeOrder");
 const read=()=>{try{return JSON.parse(localStorage.getItem("pubGrillCart")||"[]")}catch{return[]}};
 const write=items=>localStorage.setItem("pubGrillCart",JSON.stringify(items));
 const money=n=>"KES "+Number(n).toFixed(2);
 function render(){
  const items=read(); itemsEl.innerHTML=""; let total=0;
  emptyEl.hidden=items.length>0; checkout.hidden=items.length===0;
  items.forEach((item,index)=>{
   total+=Number(item.price)*item.quantity;
   const row=document.createElement("div"); row.className="cart-line";
   const title=document.createElement("div"); const strong=document.createElement("strong");strong.textContent=item.name;title.append(strong);
   const price=document.createElement("small");price.textContent=money(item.price)+" each";title.append(price);
   const qty=document.createElement("div");qty.className="qty-controls";
   const minus=document.createElement("button");minus.type="button";minus.textContent="−";minus.setAttribute("aria-label","Decrease quantity");
   const val=document.createElement("span");val.textContent=item.quantity;
   const plus=document.createElement("button");plus.type="button";plus.textContent="+";
   const remove=document.createElement("button");remove.type="button";remove.textContent="Remove";remove.className="link-button danger-text";
   minus.onclick=()=>{const a=read();a[index].quantity--;if(a[index].quantity<=0)a.splice(index,1);write(a);render();};
   plus.onclick=()=>{const a=read();if(a[index].quantity<50)a[index].quantity++;write(a);render();};
   remove.onclick=()=>{const a=read();a.splice(index,1);write(a);render();};
   qty.append(minus,val,plus,remove); const subtotal=document.createElement("strong");subtotal.textContent=money(item.price*item.quantity);
   row.append(title,qty,subtotal);itemsEl.append(row);
  });
  totalEl.textContent=money(total);
 }
 place?.addEventListener("click",async()=>{
  const items=read();if(!items.length)return;
  place.disabled=true;place.textContent="Submitting…";
  try{
   const response=await fetch(window.CART_ENDPOINT,{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":window.CSRF_TOKEN},body:JSON.stringify({items:items.map(i=>({product_id:i.product_id,quantity:i.quantity})),order_type:document.getElementById("orderType").value,special_instructions:document.getElementById("instructions").value})});
   const data=await response.json();
   if(!response.ok)throw new Error(data.error||"Could not place order.");
   write([]);window.location.href="/my-orders";
  }catch(error){alert(error.message);place.disabled=false;place.textContent="Place order";}
 });
 render();
});
