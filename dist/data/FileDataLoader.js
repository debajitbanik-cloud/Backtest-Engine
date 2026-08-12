"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.FileDataLoader = void 0;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
/**
 * Loads OHLCV data from local CSV or JSON files.
 * Expected CSV format: timestamp,open,high,low,close,volume
 */
class FileDataLoader {
    dataDir;
    constructor(dataDir = './data/shared') {
        this.dataDir = dataDir;
    }
    async fetchOHLCV(options) {
        const { symbol, timeframe, limit, startTime, endTime } = options;
        const filePath = this.getFilePath(symbol, timeframe);
        if (!fs.existsSync(filePath)) {
            throw new Error(`Data file not found: ${filePath}`);
        }
        const data = await this.loadFile(filePath, symbol, timeframe);
        let filtered = data;
        if (startTime) {
            filtered = filtered.filter(d => d.timestamp >= startTime);
        }
        if (endTime) {
            filtered = filtered.filter(d => d.timestamp <= endTime);
        }
        if (limit) {
            filtered = filtered.slice(-limit);
        }
        return filtered;
    }
    async fetchLatest(symbol, timeframe) {
        const data = await this.fetchOHLCV({ symbol, timeframe, limit: 1 });
        return data.length > 0 ? data[data.length - 1] : null;
    }
    async isSupported(symbol) {
        for (const tf of ['1m', '5m', '15m', '1h']) {
            if (fs.existsSync(this.getFilePath(symbol, tf)))
                return true;
        }
        return false;
    }
    async saveOHLCV(data) {
        if (data.length === 0)
            return;
        const symbol = data[0].symbol;
        const timeframe = data[0].timeframe;
        const filePath = this.getFilePath(symbol, timeframe);
        if (!fs.existsSync(this.dataDir)) {
            fs.mkdirSync(this.dataDir, { recursive: true });
        }
        // Save as JSON for simplicity
        fs.writeFileSync(filePath.replace('.csv', '.json'), JSON.stringify(data, null, 2));
    }
    getFilePath(symbol, timeframe) {
        const normalizedSymbol = symbol.replace('/', '_').toUpperCase();
        const basePath = path.join(this.dataDir, `${normalizedSymbol}_${timeframe}`);
        // Try .json first, then .csv
        const jsonPath = `${basePath}.json`;
        if (fs.existsSync(jsonPath))
            return jsonPath;
        return `${basePath}.csv`;
    }
    async loadFile(filePath, symbol, timeframe) {
        if (filePath.endsWith('.json')) {
            const content = fs.readFileSync(filePath, 'utf-8');
            const parsed = JSON.parse(content);
            // Convert ISO timestamp strings to Unix ms numbers
            return parsed.map((d) => ({
                ...d,
                timestamp: d.timestamp ? (typeof d.timestamp === 'number'
                    ? d.timestamp
                    : Date.parse(d.timestamp)) : Date.now()
            }));
        }
        // CSV
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.trim().split('\n');
        const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
        return lines.slice(1).map((line) => {
            const values = line.split(',');
            const row = {};
            headers.forEach((h, i) => (row[h] = values[i]));
            return {
                symbol,
                timeframe,
                timestamp: parseInt(row.timestamp || row.time || row.date),
                open: parseFloat(row.open),
                high: parseFloat(row.high),
                low: parseFloat(row.low),
                close: parseFloat(row.close),
                volume: parseFloat(row.volume || '0'),
            };
        });
    }
}
exports.FileDataLoader = FileDataLoader;
//# sourceMappingURL=FileDataLoader.js.map