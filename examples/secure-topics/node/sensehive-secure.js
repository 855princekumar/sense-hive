// Publish to a SenseHive secure topic from Node.js or a Node-RED function node.
// Protocol: docs/SECURE-TOPICS.md. Built-in crypto only.
//
// Node.js:   const { seal } = require('./sensehive-secure');
//            client.publish(topic, seal(KEY_HEX, KID, topic, JSON.stringify({ temp: 21.5 })));
//
// Node-RED:  in a function node (Setup tab: add module "crypto"), paste the seal()
//            function below, then
//                msg.payload = seal(env.get('SH_KEY'), env.get('SH_KID'), msg.topic, JSON.stringify(msg.payload));
//                return msg;
//            and wire it to an "mqtt out" node. Keep the key in an environment variable, not in the flow.
//
// Command line (used by SenseHive's tests): node sensehive-secure.js <key hex> <kid> <topic> <payload>
'use strict';
const crypto = require('crypto');

function seal(keyHex, kid, topic, payload, t) {
  const key = Buffer.from(keyHex, 'hex');
  const encKey = crypto.createHmac('sha256', key).update('sst1 enc').digest();
  const macKey = crypto.createHmac('sha256', key).update('sst1 mac').digest();
  const nonce = crypto.randomBytes(16);
  const time = t === undefined ? Math.floor(Date.now() / 1000) : t;
  const cipher = crypto.createCipheriv('aes-256-ctr', encKey, nonce);
  const ct = Buffer.concat([cipher.update(Buffer.from(payload)), cipher.final()]);
  const zero = Buffer.from([0]);
  const signed = Buffer.concat([Buffer.from('sst1'), zero, Buffer.from(topic), zero, Buffer.from(kid), zero,
    Buffer.from(String(time)), zero, nonce, ct]);
  const tag = crypto.createHmac('sha256', macKey).update(signed).digest().subarray(0, 16);
  return JSON.stringify({ v: 1, k: kid, t: time, i: nonce.toString('base64'), c: ct.toString('base64'), m: tag.toString('base64') });
}

module.exports = { seal };

if (require.main === module) {
  const [keyHex, kid, topic, payload] = process.argv.slice(2);
  process.stdout.write(seal(keyHex, kid, topic, payload));
}
