/**
 * midscene_send.js — 用 Midscene 视觉 AI 在手机上发微信
 * 用法: node midscene_send.js "联系人" "消息内容" [device_id]
 *
 * 设备选择优先级:
 *   1. 命令行第三个参数
 *   2. 环境变量 ADB_DEVICE_ID
 *   3. 当 adb 只检测到一台 online 设备时自动选用
 *   4. 否则报错并打印当前设备列表
 *
 * AI 配置通过环境变量:
 *   MIDSCENE_MODEL_BASE_URL, MIDSCENE_MODEL_API_KEY
 *   MIDSCENE_MODEL_NAME, MIDSCENE_MODEL_FAMILY
 *   MIDSCENE_MODEL_REASONING_ENABLED
 */
const { execSync } = require('child_process');

function listOnlineDevices() {
  const out = execSync('adb devices', { encoding: 'utf8', timeout: 5000 });
  const lines = out.split('\n').slice(1);  // 跳过 "List of devices attached"
  const devices = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const parts = trimmed.split(/\s+/);
    if (parts.length >= 2 && parts[1] === 'device') {
      devices.push(parts[0]);
    }
  }
  return devices;
}

function pickDeviceId(argDeviceId) {
  if (argDeviceId) return argDeviceId;
  if (process.env.ADB_DEVICE_ID) return process.env.ADB_DEVICE_ID;

  const online = listOnlineDevices();
  if (online.length === 1) {
    console.log(`[device] 自动选用唯一在线设备: ${online[0]}`);
    return online[0];
  }
  if (online.length === 0) {
    throw new Error('没有 online 的 adb 设备。请连接设备并 `adb devices` 确认状态');
  }
  throw new Error(
    `检测到 ${online.length} 台在线设备 (${online.join(', ')})。` +
    `请通过环境变量 ADB_DEVICE_ID 或命令行第三参数指定`
  );
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForDevice(deviceId, maxWait = 20) {
  for (let i = 0; i < maxWait; i++) {
    const online = listOnlineDevices();
    if (online.includes(deviceId)) return true;
    try { execSync('adb reconnect', { encoding: 'utf8', timeout: 5000, stdio: 'ignore' }); }
    catch (_) { /* ignore */ }
    await sleep(2000);
  }
  return false;
}

async function main(contact, message, argDeviceId) {
  const deviceId = pickDeviceId(argDeviceId);

  console.log(`📱 等待设备 ${deviceId} 连接...`);
  if (!await waitForDevice(deviceId)) {
    throw new Error(`设备 ${deviceId} 连接不上`);
  }

  console.log(`📤 连接 Midscene...`);
  let agentFromAdbDevice;
  try {
    ({ agentFromAdbDevice } = require('@midscene/android'));
  } catch (e) {
    throw new Error(
      '未安装 @midscene/android。请在项目目录或 tools/ 目录运行: npm i @midscene/android'
    );
  }
  const agent = await agentFromAdbDevice(deviceId);

  console.log(`📤 打开微信搜 ${contact}...`);
  await agent.aiAction(
    `Open WeChat on the phone, tap the search bar at the top, search for contact "${contact}", ` +
    `open their chat, type the message "${message}" in the input box, then press send.`,
    { deepThink: false }
  );

  console.log(`✅ 发送完成`);
  process.exit(0);
}

const [contact, message, argDeviceId] = process.argv.slice(2);
if (!contact || !message) {
  console.log('用法: node midscene_send.js "联系人" "消息内容" [device_id]');
  process.exit(1);
}

main(contact, message, argDeviceId).catch(e => {
  console.error('❌ 失败:', e.message);
  process.exit(1);
});
