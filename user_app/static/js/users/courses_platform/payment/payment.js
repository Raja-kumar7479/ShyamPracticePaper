const PAGE_DATA = document.getElementById('pageData').dataset;

let rzp = null;

function initiatePayment() {
  setTimeout(() => {
    document.getElementById('loader-overlay').classList.add('fade-out');
    setTimeout(() => {
      openRazorpay();
    }, 1000);
  }, 2000);
}

function openRazorpay() {
  rzp = window.sppCheckout.open({
    key: PAGE_DATA.razorpayKeyId,
    amount: PAGE_DATA.amount,
    description: "Course Purchase",
    orderId: PAGE_DATA.razorpayOrderId,
    name: PAGE_DATA.username,
    email: PAGE_DATA.email,
    contact: PAGE_DATA.phone,
    onSuccess: function (response) {
      document.getElementById('payment_id').value = response.razorpay_payment_id;
      document.getElementById('razorpay_signature').value = response.razorpay_signature;

      fadeOutWatermark();
      showPostPaymentLoader();

      setTimeout(() => {
        document.getElementById('payment_success_form').submit();
      }, 2000);
    },
    onDismiss: function () {
      window.location.replace(PAGE_DATA.addCartUrl);
    }
  });
}

function fadeOutWatermark() {
  const wm = document.getElementById('watermark-container');
  if (wm) {
    wm.classList.add('fade-out');
  }
}

function showPostPaymentLoader() {
  const loader = document.getElementById('post-payment-loader');
  if (loader) {
    loader.style.display = 'flex';
  }
}
