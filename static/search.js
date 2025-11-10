const search = document.getElementById("userSearch");
search.addEventListener("input",function(){
    const events = document.querySelectorAll("ul li");
    const searchLower = search.value.toLowerCase();
    events.forEach(function(e){
        const eventName = e.textContent.toLowerCase();
        if (eventName.includes(searchLower)){
            e.style.display="";
        } else {
            e.style.display="none";
        }
    })
})