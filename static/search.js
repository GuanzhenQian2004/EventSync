const search = document.getElementById("userSearch");
search.addEventListener("input",function(){
    const events = document.querySelectorAll("ul li");
    const searchLower = search.value.toLowerCase();
    events.forEach(function(event){
        const eventName = event.textContent.toLowerCase();
    })
})