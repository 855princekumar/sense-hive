// React for SenseHive's pages, bundled locally by esbuild into static/vendor/react.js
// (React 19 ships no UMD files). The pages use the globals React and ReactDOM,
// as they did with the UMD builds; nothing is loaded from a CDN.
import * as React from 'react';
import * as ReactDOM from 'react-dom';
import * as ReactDOMClient from 'react-dom/client';

window.React = React;
window.ReactDOM = Object.assign({}, ReactDOM, ReactDOMClient);
