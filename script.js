function main() {
  // Kinto server url
  var server = "https://kinto.dev.mozaws.net/v1";
  // Basic Authentication
  var headers = {};
  // Bucket id
  var bucket = "kintobot";
  // Collection id
  var collection = "wall";
  // Pusher app key
  var pusher_key = "01a9feaaf9ebb120d1a6";
  // Max initial number of records
  var limit = 100;
  // Refresh rate
  var refreshRate = 7000;

  var contents = [];
  var queue = [];

  // Fetch from kinto.
  var url = `${server}/buckets/${bucket}/collections/${collection}/records?_limit=${limit}`;
  fetch(url, {headers: headers})
   .then(function (response) {
     return response.json();
   })
   .then(function (result) {
     if (result.data) {
       contents = result.data;
       showContent(contents[0]);
     }
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
    var newrecords = data.map(function (change) { return change.new; });
    var wasEmpty = contents.length === 0;
    contents = newrecords.concat(contents);
    queue = newrecords.concat(queue);
    if (wasEmpty) {
       showContent(contents[0]);
    }
  });
  channel.bind('delete', function(data) {
    var deletedIds = data.map(function (change) { return change.old.id; });
    contents = contents.filter(function (record) { return deletedIds.indexOf(record.id) < 0; });
    queue = queue.filter(function (record) { return deletedIds.indexOf(record.id) < 0; });
  });

  // Preload media
  function preload(record) {
    var isURL = /^http(.*)(gif|jpg|jpeg)$/.test(record.text);
    if (isURL || record.attachment) {
      var location = isURL ? record.text : record.attachment.location;
      if (isURL || /^image/.test(record.attachment.mimetype)) {
        var image = new Image();
        image.src = location;
      }
    }
  }

  // Render HTML.
  function showContent(record) {
    var entry;
    var isURL = /^http(.*)(gif|jpg|jpeg)$/.test(record.text);
    if (isURL || record.attachment) {
      var location = isURL ? record.text : record.attachment.location;
      var attr = "src";
      var template;
      if (isURL || /^image/.test(record.attachment.mimetype)) {
        template = "image-tpl";
      }
      else if (/^audio/.test(record.attachment.mimetype)) {
        template = "audio-tpl";
      }
      else if (/^video/.test(record.attachment.mimetype)) {
        template = "video-tpl";
      }
      else {
        template = "file-tpl";
        attr = "href";
      }
      var tpl = document.getElementById(template);
      entry = tpl.content.cloneNode(true);
      entry.querySelector(".attachment").setAttribute(attr, location);
    }
    else {
      var tpl = document.getElementById("text-tpl");
      entry = tpl.content.cloneNode(true);
      entry.querySelector(".msg").textContent = record.text;
    }
    entry.querySelector(".author").textContent = record.from.first_name;

    // Replace current with new one.
    var wall = document.querySelector("#wall");
    wall.innerHTML = "";
    wall.appendChild(entry);

    // Consume queue.
    if (queue.length > 0) {
      record = queue[0];
      queue = queue.slice(1);
    }
    // Restart with whole list when done.
    if (queue.length === 0) {
      queue = contents;
    }

    // Preload next record
    preload(record);

    // Auto-refresh.
    setTimeout(showContent.bind(undefined, record), refreshRate);

    // Toggle progress bar.
    document.querySelector("#progress").classList.toggle('run');
  }
}

window.addEventListener("DOMContentLoaded", main);
