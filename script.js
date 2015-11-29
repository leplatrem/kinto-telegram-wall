function main() {
  // Kinto server url
  var server = "http://95.85.60.144:8888/v1";
  // Basic Authentication
  var headers = {};
  // Bucket id
  var bucket = "kintobot";
  // Collection id
  var collection = "wall";
  // Pusher app key
  var pusher_key = "ccbbb57423e56f4db774";
  // Max number of records
  var limit = 100;

  var wall = document.querySelector("#wall");

  // Fetch from kinto.
  var url = `${server}/buckets/${bucket}/collections/${collection}/records?_limit=${limit}`;
  fetch(url, {headers: headers})
   .then(function (response) {
     return response.json();
   })
   .then(function (result) {
     wall.innerHTML = "";
     result.data.forEach(function(record) {
       wall.appendChild(renderRecord(record));
     });
   })
   .catch(function (error) {
     document.getElementById("error").textContent = error.toString();
   });


  // Live changes.
  var pusher = new Pusher(pusher_key, {
    encrypted: true
  });
  var channelName = `${bucket}-${collection}-record`;
  var channel = pusher.subscribe(channelName);
  channel.bind('create', function(data) {
    data.forEach(function (change) {
      wall.insertBefore(renderRecord(change.new), wall.firstChild);
    });
  });


  function renderRecord(record) {
    var entry;
    if (record.attachment) {
      if (/^image/.test(record.attachment.mimetype)) {
        var tpl = document.getElementById("image-tpl");
        entry = tpl.content.cloneNode(true);
        entry.querySelector(".attachment").setAttribute("href", record.attachment.location);
        entry.querySelector(".attachment img").setAttribute("src", record.attachment.location);
      }
      else if (/^audio/.test(record.attachment.mimetype)) {
        var tpl = document.getElementById("audio-tpl");
        entry = tpl.content.cloneNode(true);
        entry.querySelector(".attachment").setAttribute("src", record.attachment.location);
      }
      else if (/^video/.test(record.attachment.mimetype)) {
        var tpl = document.getElementById("video-tpl");
        entry = tpl.content.cloneNode(true);
        entry.querySelector(".attachment").setAttribute("src", record.attachment.location);
      }
      else {
        var tpl = document.getElementById("attachment-tpl");
        entry = tpl.content.cloneNode(true);
        entry.querySelector(".download").setAttribute("href", record.attachment.location);
      }
    }
    else {
      var tpl = document.getElementById("text-tpl");
      entry = tpl.content.cloneNode(true);
      entry.querySelector(".msg").textContent = record.text;
    }

    entry.querySelector(".date").textContent = moment(record.date, "X").fromNow();
    entry.querySelector(".author").textContent = record.from.first_name;
    return entry;
  }
}

window.addEventListener("DOMContentLoaded", main);
