const Sendbutton = document.querySelector("#sendBtn"); // 发送按钮
const UserInput = document.querySelector("#inputText"); // 用户输入框
const chatContainer = document.querySelector(".chatList"); // 聊天容器
const chatArea = document.querySelector(".chatArea"); // 聊天列表
let Status = 0;
const userMessage = (message) => {
  return `<div class="self">
                    <div class="message">
                        <div class="markdown-body">${message}</div>
                    </div>
                    <img class="head" src="../static/img/user.jpg" alt="user">
                </div>`;
};
const botMessage = (message) => {
  return `<div class="robot">
                    <img class="head" src="../static/img/tina.jpg" alt="tina">
                    <div class="message">
                        <div class="markdown-body">${message}</div>
                    </div>
                </div>`;
};

let currentBotMessage = "";

function InputListener(self) {
  if (self.value.trim() === "" || Status === 1) {
    Sendbutton.disabled = true;
    Sendbutton.classList = "";
    return;
  }
  Sendbutton.disabled = false;
  Sendbutton.classList = "has-text";
}

function sendMessage(self) {
  const userInput = UserInput.value.trim();
  if (userInput === "" || Status === 1) return;
  Sendbutton.disabled = true;
  Status = 1;
  Sendbutton.classList = "";
  chatContainer.innerHTML += userMessage(`${marked.parse(userInput)}`);
  chatContainer.innerHTML += botMessage("...");
  UserInput.value = "";
  fetch("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: `message=${encodeURIComponent(userInput)}`,
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Network response was not ok " + response.statusText);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let data = "";
      function readStream() {
        return reader.read().then(({ done, value }) => {
          if (done) {
            return;
          }
          data += decoder.decode(value, { stream: true });
          const events = data.split("data: ");
          let botMessageList = document.querySelectorAll(".robot .message>div");
          events.forEach((event) => {
            if (event.trim() !== "" && event.trim() !== "\n\n") {
              const trimmedEvent = event.trim();
              if (trimmedEvent !== currentBotMessage) {
                currentBotMessage = trimmedEvent;
                botMessageList[
                  botMessageList.length - 1
                ].innerHTML = `${marked.parse(currentBotMessage)}`;
                hljs.highlightAll();
                scrollToBottom();
              }
            }
          });
          data = events.pop(); // 保留最后一个不完整的事件
          Sendbutton.disabled = false;
          Status = 0;
          return readStream();
        });
      }
      return readStream();
    })
    .catch((error) => {
      console.error("Error:", error);
    });
}

// 监听输入框的变化
UserInput.addEventListener("keydown", function (event) {
  if (event.key === "Enter") {
    event.preventDefault();
    sendMessage(Sendbutton);
  }
});
// 自动滚动到聊天容器的底部
function scrollToBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

// 初始化聊天容器
window.onload = function () {
  chatArea.scrollTop = chatArea.scrollHeight;
};
