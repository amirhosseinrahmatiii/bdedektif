const apiBase = ""; // aynı domain için boş bırak

document.getElementById('fileInput').addEventListener('change', (e) => {
  uploadFiles(e.target.files);
});

const dropzone = document.getElementById('dropzone');
dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.style.background = '#fafafa';
});
dropzone.addEventListener('dragleave', () => dropzone.style.background = '');
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.style.background = '';
  uploadFiles(e.dataTransfer.files);
});

function uploadFiles(files) {
  if (!files.length) return;
  const fd = new FormData();
  for (let f of files) fd.append('files', f);

  const xhr = new XMLHttpRequest();
  xhr.open('POST', `${apiBase}/api/new-upload`);
  
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const percent = (e.loaded / e.total) * 100;
      document.getElementById('progressBar').style.width = percent + '%';
    }
  };

  xhr.onload = () => {
    document.getElementById('status').textContent = xhr.responseText;
  };

  xhr.send(fd);
}
