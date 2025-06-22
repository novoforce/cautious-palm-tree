// Global variables
const sessionId = Math.random().toString().substring(10);
const ws_url = "ws://" + window.location.host + "/ws/" + sessionId;
let websocket = null;
let is_audio = false; // User input is audio
let agentWantsAudioOutput = true; // Agent output includes audio
let currentMessageId = null; // Track the current message ID during a conversation turn
let currentUserTranscriptionMessageId = null; // Track current USER transcription message ID #ashish

// Get DOM elements
const messageForm = document.getElementById("messageForm");
const messageInput = document.getElementById("message");
const messagesDiv = document.getElementById("messages");
const statusDot = document.getElementById("status-dot");
const connectionStatus = document.getElementById("connection-status");
const typingIndicator = document.getElementById("typing-indicator");
const startAudioButton = document.getElementById("startAudioButton");
const stopAudioButton = document.getElementById("stopAudioButton");
const recordingContainer = document.getElementById("recording-container");
const toggleAgentVoiceButton = document.getElementById("toggleAgentVoiceButton");

// WebSocket handlers
function connectWebsocket() {
  // If there's an existing websocket, close it before creating a new one
  if (websocket) {
    websocket.onclose = () => {}; // Prevent the default onclose handler from firing for this deliberate close
    websocket.close();
    websocket = null;
    console.log("Previous WebSocket connection closed for mode change.");
  }

  // Connect websocket
  const wsQuery = `?is_audio=${is_audio}&agent_wants_audio_output=${agentWantsAudioOutput}`;
  const sessionId = Math.random().toString().substring(10);
// Determine the correct protocol (wss for https, ws for http)
// window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const protocol = 'ws:' 
  const ws_url_base = `${protocol}//${window.location.host}/ws/${sessionId}`;
  const wsUrl = ws_url_base + wsQuery;
  console.log(`Connecting to WebSocket: ${wsUrl}`);
  websocket = new WebSocket(wsUrl);

  // Handle connection open
  websocket.onopen = function () {
    // Connection opened messages
    console.log("WebSocket connection opened.");
    connectionStatus.textContent = "Connected";
    statusDot.classList.add("connected");
    // Enable the Send button
    document.getElementById("sendButton").disabled = false;
    addSubmitHandler();
  };

  websocket.onmessage = function (event) {
    const message_from_server = JSON.parse(event.data);
    // console.log("[AGENT TO CLIENT] RAW: ", event.data); // For deep debugging if JSON parsing fails
    console.log("[AGENT TO CLIENT] Parsed: ", message_from_server); // General log for received message

    // --- 1. Handle User Transcription ---
    if (message_from_server.role === "user_transcription") {
      typingIndicator.classList.remove("visible"); // Agent isn't "typing" this
      const textData = message_from_server.data;
      let transcriptionElem = document.getElementById(currentUserTranscriptionMessageId);
      if (!transcriptionElem) { // First part of a new transcription
        const newTranscriptionId = "user-transc-" + Date.now() + Math.random().toString(36).substr(2, 5);
        transcriptionElem = document.createElement("p");
        transcriptionElem.id = newTranscriptionId;
        transcriptionElem.className = "user-message"; // Style like other user messages
        
        transcriptionElem.appendChild(document.createTextNode(textData)); // Append first chunk
        
        messagesDiv.appendChild(transcriptionElem);
        currentUserTranscriptionMessageId = newTranscriptionId;
      } else { // Subsequent part, append to existing element's text
        transcriptionElem.appendChild(document.createTextNode(textData)); // Append new chunk
      }
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
      return; // Processed user transcription, exit this handler invocation
    }

    // --- 2. Show Typing Indicator for Model's activity (if not turn complete) ---
    if (
      !message_from_server.turn_complete && // Must not be turn_complete
      message_from_server.role === "model" && // Only for model's own messages/audio
      (message_from_server.mime_type === "text/plain" || message_from_server.mime_type === "audio/pcm")
    ) {
      typingIndicator.classList.add("visible");
    }

    // --- 3. Handle Turn Completion ---
    if (message_from_server.turn_complete === true || message_from_server.interrupted === true) { // Check both
      currentMessageId = null; // Reset for agent's next text response
      currentUserTranscriptionMessageId = null; // Reset for user's next transcription
      typingIndicator.classList.remove("visible");
      console.log("[TURN] Complete or Interrupted.");
      return; // Processed turn_complete or interrupted, exit
    }

    // --- 4. Handle Agent Audio Output ---
    if (message_from_server.mime_type === "audio/pcm" && audioPlayerNode && message_from_server.role === "model" && agentWantsAudioOutput) {
      console.log("[AUDIO PLAYER] Received agent audio data. Current agent msg ID:", currentMessageId);
      audioPlayerNode.port.postMessage(base64ToArray(message_from_server.data));
      
      // Attempt to add audio icon to the corresponding text message, if it exists
      if (currentMessageId && agentWantsAudioOutput) { // Also check agentWantsAudioOutput here
        const messageElem = document.getElementById(currentMessageId);
        // Check if audio icon already exists to avoid duplicates if audio comes before all text
        if (messageElem && !messageElem.querySelector(".audio-icon")) { 
          const audioIcon = document.createElement("span");
          audioIcon.className = "audio-icon";
          // Prepend icon. Ensure there's a space if text is already there.
          if (messageElem.firstChild) {
            messageElem.insertBefore(audioIcon, messageElem.firstChild);
            messageElem.insertBefore(document.createTextNode(" "), audioIcon.nextSibling);
          } else {
            messageElem.appendChild(audioIcon);
            messageElem.appendChild(document.createTextNode(" "));
          }
        }
      }
    }

    if (message_from_server.mime_type === "image/png" && message_from_server.role === "model") {
      console.log("!!! DETECTED IMAGE MESSAGE !!!", message_from_server); 
      typingIndicator.classList.remove("visible"); // Hide indicator as content arrives
      
      const messageContainer = document.createElement("div");
      messageContainer.className = "agent-message"; // Use the same styling as agent text messages

      // Optional: Add a caption if provided
      if (message_from_server.caption) {
        const captionElem = document.createElement("p");
        captionElem.className = "image-caption";
        captionElem.textContent = message_from_server.caption;
        messageContainer.appendChild(captionElem);
      }
      
      const imageElem = document.createElement("img");
      imageElem.src = message_from_server.data; // The data is the URL
      imageElem.alt = "Generated Chart";
      imageElem.className = "chat-image";
      
      // Add onload handler to scroll after image has loaded and dimensions are known
      imageElem.onload = () => {
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
      };

      messageContainer.appendChild(imageElem);
      messagesDiv.appendChild(messageContainer);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }



    // --- 5. Handle Agent Text Output ---
    if (message_from_server.mime_type === "text/plain" && message_from_server.role === "model") {
      typingIndicator.classList.remove("visible"); // Hide indicator as text arrives
      let messageElem = document.getElementById(currentMessageId);
      if (!messageElem) { // First part of a new agent text message
        const newMessageId = "agent-msg-" + Date.now() + Math.random().toString(36).substr(2, 5);
        messageElem = document.createElement("p");
        messageElem.id = newMessageId;
        messageElem.className = "agent-message";
        
        if (agentWantsAudioOutput) { // If agent voice output is enabled, prepend an audio icon placeholder
          const audioIcon = document.createElement("span");
          audioIcon.className = "audio-icon";
          messageElem.appendChild(audioIcon);
          messageElem.appendChild(document.createTextNode(" ")); // Space after icon
        }
        
        messageElem.appendChild(document.createTextNode(message_from_server.data)); // Add first text chunk
        messagesDiv.appendChild(messageElem);
        currentMessageId = newMessageId; // Set current ID for subsequent appends
      } else { // Subsequent part, append to existing agent message element
        messageElem.appendChild(document.createTextNode(message_from_server.data)); // Append new text chunk
      }
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
    
    // --- 6. Handle System Error Messages from Backend ---
    if (message_from_server.role === "system" && message_from_server.error) {
        console.error("Error from server:", message_from_server.error);
        const errorElem = document.createElement("p");
        errorElem.className = "error-message"; // You might want to style this class
        errorElem.textContent = "System Error: " + message_from_server.error;
        messagesDiv.appendChild(errorElem);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        typingIndicator.classList.remove("visible");
        return;
    }
  }; // End of websocket.onmessage

  // Handle connection close
  websocket.onclose = function () {
    console.log("WebSocket connection closed.");
    document.getElementById("sendButton").disabled = true;
    connectionStatus.textContent = "Disconnected. Reconnecting...";
    statusDot.classList.remove("connected");
    typingIndicator.classList.remove("visible");
    // This onclose is for unexpected closes, try to reconnect
    setTimeout(function () {
      console.log("Reconnecting...");
      connectWebsocket();
    }, 5000);
  };

  websocket.onerror = function (e) {
    console.error("WebSocket error: ", e);
    connectionStatus.textContent = "Connection error";
    statusDot.classList.remove("connected");
    typingIndicator.classList.remove("visible");
  };
}

connectWebsocket(); // Initial connection

// Add submit handler to the form
function addSubmitHandler() {
  messageForm.onsubmit = function (e) {
    e.preventDefault();
    const message = messageInput.value;
    if (message) {
      const p = document.createElement("p");
      p.textContent = message;
      p.className = "user-message";
      messagesDiv.appendChild(p);
      messageInput.value = "";
      // Show typing indicator after sending message
      typingIndicator.classList.add("visible");
      sendMessage({
        mime_type: "text/plain",
        data: message,
        role: "user",
      });
      console.log("[CLIENT TO AGENT] " + message);
      // Scroll down to the bottom of the messagesDiv
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
    return false;
  };
}

// Send a message to the server as a JSON string
function sendMessage(message) {
  if (websocket && websocket.readyState == WebSocket.OPEN) {
    const messageJson = JSON.stringify(message);
    websocket.send(messageJson);
  }
}

// Decode Base64 data to Array
function base64ToArray(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

/**
 * Audio handling
 */
let audioPlayerNode;
let audioPlayerContext;
let audioRecorderNode;
let audioRecorderContext;
let micStream;
let isRecording = false;

// Import the audio worklets
import { startAudioPlayerWorklet } from "./audio-player.js";
import { startAudioRecorderWorklet } from "./audio-recorder.js";

// Start audio
function startAudio() {
  // Start audio output
  startAudioPlayerWorklet().then(([node, ctx]) => {
    audioPlayerNode = node;
    audioPlayerContext = ctx;
  });
  // Start audio input
  startAudioRecorderWorklet(audioRecorderHandler).then(
    ([node, ctx, stream]) => {
      audioRecorderNode = node;
      audioRecorderContext = ctx;
      micStream = stream;
      isRecording = true;
    }
  );
}

// Stop audio recording
function stopAudio() {
  if (audioRecorderNode) {
    audioRecorderNode.disconnect();
    audioRecorderNode = null;
  }
  if (audioRecorderContext) {
    audioRecorderContext
      .close()
      .catch((err) => console.error("Error closing audio context:", err));
    audioRecorderContext = null;
  }
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }
  isRecording = false;
}

// Start the audio only when the user clicked the button
// (due to the gesture requirement for the Web Audio API)
startAudioButton.addEventListener("click", () => {
  startAudioButton.disabled = true;
  startAudioButton.textContent = "Voice Enabled";
  startAudioButton.style.display = "none";
  stopAudioButton.style.display = "inline-block";
  recordingContainer.style.display = "flex";
  startAudio();
  is_audio = true; // User input is audio
  // Add class to messages container to enable audio styling (optional, for specific UI effects)
  // messagesDiv.classList.add("audio-enabled"); 
  connectWebsocket(); // reconnect with the new is_audio mode
});

// Stop audio recording when stop button is clicked
stopAudioButton.addEventListener("click", () => {
  stopAudio();
  stopAudioButton.style.display = "none";
  startAudioButton.style.display = "inline-block";
  startAudioButton.disabled = false;
  startAudioButton.textContent = "Enable Voice";
  recordingContainer.style.display = "none";
  // Remove audio styling class (optional)
  // messagesDiv.classList.remove("audio-enabled");
  is_audio = false; // User input is not audio
  connectWebsocket(); // reconnect with new is_audio mode
});

// Toggle agent voice output button
toggleAgentVoiceButton.addEventListener("click", () => {
  agentWantsAudioOutput = !agentWantsAudioOutput;
  toggleAgentVoiceButton.textContent = agentWantsAudioOutput ? "Agent Voice: ON" : "Agent Voice: OFF";
  connectWebsocket(); // Reconnect with the new agent voice output preference
});

// Audio recorder handler
function audioRecorderHandler(pcmData) {
  // Only send data if we're still recording
  if (!isRecording) return;
  // Send the pcm data as base64
  sendMessage({
    mime_type: "audio/pcm",
    data: arrayBufferToBase64(pcmData),
  });
  // Log every few samples to avoid flooding the console
  if (Math.random() < 0.01) {
    // Only log ~1% of audio chunks
    console.log("[CLIENT TO AGENT] sent audio data");
  }
}

// Encode an array buffer with Base64
function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}