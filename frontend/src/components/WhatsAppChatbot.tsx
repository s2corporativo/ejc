import React, { useState } from "react";

interface Message {
  id: number;
  text: string;
  sender: "user" | "bot";
  timestamp: string;
}

const WhatsAppChatbot: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      text: "Olá! 👋 Sou o Assistente Jurídico do EJC. Como posso ajudá-lo?",
      sender: "bot",
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isOnline, setIsOnline] = useState(true);

  const handleSendMessage = () => {
    if (!inputValue.trim()) return;

    const newMessage: Message = {
      id: messages.length + 1,
      text: inputValue,
      sender: "user",
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages([...messages, newMessage]);
    setInputValue("");

    // Simular resposta do bot
    setTimeout(() => {
      const botResponses = [
        "Seu processo #1029 está em andamento. Próximo prazo: 15 de julho.",
        "Você tem 2 alertas de liquidez pendentes. Deseja revisar?",
        "A taxa de êxito do seu caso tributário é de 82%. Recomendo prosseguir.",
        "Conectando com o Dr. Clovis... Um momento, por favor.",
      ];
      const randomResponse =
        botResponses[Math.floor(Math.random() * botResponses.length)];

      const botMessage: Message = {
        id: messages.length + 2,
        text: randomResponse,
        sender: "bot",
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, botMessage]);
    }, 500);
  };

  return (
    <div className="fixed bottom-8 right-8 w-96 h-screen md:h-96 rounded-2xl shadow-2xl bg-gradient-to-br from-stone-900 to-stone-950 border border-warn-900/30 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-warn-700 to-warn-800 p-4 flex justify-between items-center">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center text-warn-700 font-bold">
            ⚖️
          </div>
          <div>
            <h3 className="text-white font-bold">Assistente EJC</h3>
            <p className="text-xs text-warn-100">
              {isOnline ? "🟢 Online" : "🔴 Offline"}
            </p>
          </div>
        </div>
        <button className="text-white hover:text-warn-200 transition-colors">
          ✕
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-xs px-4 py-2 rounded-lg ${
                msg.sender === "user"
                  ? "bg-warn-600 text-white rounded-br-none"
                  : "bg-stone-800 text-stone-200 rounded-bl-none border border-warn-900/20"
              }`}
            >
              <p className="text-sm">{msg.text}</p>
              <p className="text-xs mt-1 opacity-70">{msg.timestamp}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="px-4 py-3 border-t border-warn-900/20 space-y-2">
        <p className="text-xs text-stone-400 mb-2">Ações rápidas:</p>
        <div className="flex flex-wrap gap-2">
          {["Status do Caso", "Prazos", "Liquidez", "Falar com Advogado"].map(
            (action) => (
              <button
                key={action}
                className="text-xs bg-stone-800 hover:bg-stone-700 text-warn-400 px-3 py-1 rounded-full transition-colors"
              >
                {action}
              </button>
            ),
          )}
        </div>
      </div>

      {/* Input */}
      <div className="p-4 border-t border-warn-900/20 flex space-x-2">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
          placeholder="Digite sua mensagem..."
          className="flex-1 bg-stone-800 border border-warn-900/20 text-white px-4 py-2 rounded-lg focus:outline-none focus:ring-1 focus:ring-warn-500 text-sm"
        />
        <button
          onClick={handleSendMessage}
          className="btn-gold px-4 py-2 font-bold"
        >
          ➤
        </button>
      </div>
    </div>
  );
};

export default WhatsAppChatbot;
