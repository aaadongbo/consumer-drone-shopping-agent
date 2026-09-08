(function () {
  "use strict";

  // Credential-free browser boundary: the only request target is the existing
  // Conversation API endpoint supplied by the page host.
  function mount(root) {
    var endpoint = root.dataset.apiEndpoint || "/v1/conversation/turn";
    var origin = root.dataset.apiOrigin || window.location.origin;
    // Host configuration: data-support-url is exposed as dataset.supportUrl.
    var supportUrl = root.dataset.supportUrl || null;
    var context = {
      store_id: root.dataset.storeId,
      product_id: root.dataset.productId,
      variant_id: root.dataset.variantId || null
    };
    var conversationId = root.dataset.conversationId || "storefront-widget";
    var sequence = 0;
    root.innerHTML =
      '<div class="presales-widget" role="region" aria-label="Product assistant">' +
      '<div class="presales-widget__messages" aria-live="polite"></div>' +
      '<form class="presales-widget__form"><input aria-label="Ask about this product" required />' +
      '<button type="submit">Ask</button></form></div>';
    var messages = root.querySelector(".presales-widget__messages");
    var form = root.querySelector("form");
    var input = form.querySelector("input");

    function show(text, kind, link, linkLabel) {
      var item = document.createElement("div");
      item.className = "presales-widget__message presales-widget__message--" + kind;
      item.textContent = text;
      if (link) {
        var anchor = document.createElement("a");
        anchor.href = link;
        anchor.textContent = linkLabel || "View product";
        anchor.target = "_self";
        item.appendChild(document.createTextNode(" "));
        item.appendChild(anchor);
      }
      messages.appendChild(item);
      return item;
    }

    function updateContext(next) {
      context = {
        store_id: next.store_id,
        product_id: next.product_id,
        variant_id: next.variant_id || null
      };
      messages.textContent = "";
      sequence = 0;
    }

    root.addEventListener("presales:navigate", function (event) {
      updateContext(event.detail || {});
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      sequence += 1;
      var text = input.value.trim();
      if (!text) return;
      show("Loading…", "loading");
      fetch(new URL(endpoint, origin).toString(), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          schema_version: "1.0",
          store_id: context.store_id,
          conversation: { conversation_id: conversationId, message_id: "widget-" + sequence },
          user_text: text,
          locale: "en-US",
          page_context: { product_id: context.product_id, variant_id: context.variant_id }
        })
      }).then(function (response) {
        if (!response.ok) throw new Error("conversation request rejected");
        return response.json();
      }).then(function (payload) {
        var body = payload.answer || payload.fallback || payload;
        var message = body.text || body.message || "I cannot verify that yet.";
        var link = root.dataset.productUrl || null;
        var messageItem = show(
          message,
          payload.outcome === "ANSWER" ? "answer" : "fallback",
          link
        );
        if (
          payload.outcome !== "ANSWER" &&
          payload.fallback &&
          payload.fallback.reason_code === "OUT_OF_SCOPE" &&
          supportUrl
        ) {
          var support = new URL(supportUrl, origin);
          if (support.origin === new URL(origin).origin) {
            var supportLink = document.createElement("a");
            supportLink.href = support.toString();
            supportLink.textContent = "Contact store support";
            supportLink.target = "_self";
            messageItem.appendChild(document.createTextNode(" "));
            messageItem.appendChild(supportLink);
          }
        }
      }).catch(function () {
        show("The storefront assistant is unavailable. Please try again.", "error");
      });
    });
  }

  document.querySelectorAll("[data-presales-widget]").forEach(mount);
}());
