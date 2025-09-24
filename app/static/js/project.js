document.addEventListener('DOMContentLoaded', function () {
  if (window.showClassPopup) {
    var classModal = new bootstrap.Modal(document.getElementById('classSelectModal'), {
      backdrop: 'static',
      keyboard: false
    });
    classModal.show();

    window.setUserClass = function (classLevel) {
      fetch('/update_class', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': window.csrf_token  // if you use CSRF protection
        },
        body: JSON.stringify({ class_level: classLevel })
      })
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            classModal.hide();
            location.reload(); // or do something else after success
          } else {
            alert('Failed to save class: ' + (data.message || 'Unknown error'));
          }
        })
        .catch(() => {
          alert('Error saving class. Please try again.');
        });
    };
  }
});
