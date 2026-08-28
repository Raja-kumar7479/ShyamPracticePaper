const PAGE_DATA = document.getElementById('pageData').dataset;

  var POPUPS = ['coupon-popup', 'phonePopup', 'billingPopup'];
  var PHONE_VERIFIED = PAGE_DATA.value;

  function setStep(active) {
    document.querySelectorAll('#steps .step').forEach(function (el) {
      var n = parseInt(el.getAttribute('data-step'), 10);
      el.classList.toggle('is-done', n < active);
      el.classList.toggle('is-active', n === active);
    });
    document.querySelectorAll('#steps .step__line').forEach(function (el) {
      el.classList.toggle('is-done', parseInt(el.getAttribute('data-line'), 10) < active);
    });
  }

  function openPopup(id, step) {
    document.getElementById('overlay').classList.add('is-open');
    document.getElementById(id).classList.add('is-open');
    document.body.classList.add('is-locked');
    if (step) setStep(step);
  }

  function showCouponPopup() { openPopup('coupon-popup'); }

  function closeCouponPopup() {
    document.getElementById('coupon-popup').classList.remove('is-open');
    document.getElementById('overlay').classList.remove('is-open');
    document.body.classList.remove('is-locked');
  }

  function openPhonePopup() {
    openPopup('phonePopup', 2);
    setTimeout(function () { document.getElementById('phone_number').focus(); }, 260);
  }

  function closeAllPopups() {
    document.getElementById('overlay').classList.remove('is-open');
    POPUPS.forEach(function (id) {
      document.getElementById(id).classList.remove('is-open');
    });
    document.body.classList.remove('is-locked');
    setStep(PHONE_VERIFIED ? 2 : 1);
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAllPopups();
  });

  if (PHONE_VERIFIED) setStep(2);

  document.getElementById('phone_number').addEventListener('input', function () {
    this.value = this.value.replace(/\D/g, '').slice(0, 10);
  });

  document.getElementById('phoneForm').addEventListener('submit', function(e) {
    const phone = document.getElementById('phone_number').value.trim();
    const phonePattern = /^[1-9][0-9]{9}$/;
    if (!phonePattern.test(phone)) {
      e.preventDefault();
      alert('Please enter a valid 10-digit phone number starting with 1-9.');
    }
  });

  window.addEventListener('load', function() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('show_billing') === 'true') {
      openPopup('billingPopup', 3);

      params.delete('show_billing');
      const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
      window.history.replaceState({}, document.title, newUrl);
    }
  });

  document.getElementById('proceed-to-pay-btn').addEventListener('click', function() {
    const loader = document.getElementById('payment-loader-overlay');
    loader.querySelector('.loader-text').textContent = 'Initiating Secure Payment...';
    loader.classList.add('is-open');
    document.getElementById('billingPopup').classList.remove('is-open');

    fetch(PAGE_DATA.createPaymentOrderUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': PAGE_DATA.csrfToken }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            loader.classList.remove('is-open');
            openRazorpay(data);
        } else {
            throw new Error(data.error || 'Failed to create payment order.');
        }
    })
    .catch(error => {
        loader.classList.remove('is-open');
        alert('Error: ' + error.message);
        closeAllPopups();
    });
  });

  function openRazorpay(paymentData) {
    window.sppCheckout.open({
      key: paymentData.razorpay_key_id,
      amount: paymentData.amount,
      description: "Course Purchase",
      orderId: paymentData.razorpay_order_id,
      name: paymentData.username,
      email: paymentData.email,
      contact: paymentData.phone,
      onSuccess: function (response) {
        document.getElementById('payment_id').value = response.razorpay_payment_id;
        document.getElementById('razorpay_signature').value = response.razorpay_signature;
        document.getElementById('order_id').value = paymentData.razorpay_order_id;

        closeAllPopups();

        const loader = document.getElementById('payment-loader-overlay');
        loader.querySelector('.loader-text').textContent = 'Payment Successful! Verifying...';
        loader.classList.add('is-open');

        document.getElementById('payment_success_form').submit();
      },
      onDismiss: function () {
        closeAllPopups();
      }
    });
  }
