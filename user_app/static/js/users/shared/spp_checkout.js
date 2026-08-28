(function () {
    'use strict';

    var BRAND_NAME = 'ShyamPracticePaper';
    var BRAND_THEME = '#992c25';
    var BRAND_LOGO = '/static/images/favicon.png';

    window.sppCheckout = {
        brandName: BRAND_NAME,
        brandTheme: BRAND_THEME,
        brandLogo: BRAND_LOGO,

        open: function (opts) {
            opts = opts || {};
            if (!window.Razorpay) {
                if (typeof opts.onUnavailable === 'function') {
                    opts.onUnavailable();
                } else {
                    alert('Payment system unavailable. Please refresh the page and try again.');
                }
                return null;
            }

            var options = {
                key: opts.key,
                amount: opts.amount,
                currency: opts.currency || 'INR',
                name: BRAND_NAME,
                description: opts.description || 'Secure Payment',
                image: opts.image || BRAND_LOGO,
                order_id: opts.orderId,
                handler: opts.onSuccess || function () {},
                prefill: {
                    name: opts.name || '',
                    email: opts.email || '',
                    contact: opts.contact || ''
                },
                theme: { color: BRAND_THEME },
                modal: {
                    ondismiss: opts.onDismiss || function () {}
                }
            };

            var rzp = new Razorpay(options);
            if (typeof opts.onFailed === 'function') {
                rzp.on('payment.failed', opts.onFailed);
            }
            rzp.open();
            return rzp;
        }
    };
})();
