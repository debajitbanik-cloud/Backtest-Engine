"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DataLoaderFactory = void 0;
const BinanceDataLoader_1 = require("./BinanceDataLoader");
const FileDataLoader_1 = require("./FileDataLoader");
class DataLoaderFactory {
    static create(type, options) {
        switch (type) {
            case 'binance':
                return new BinanceDataLoader_1.BinanceDataLoader();
            case 'file':
                return new FileDataLoader_1.FileDataLoader(options?.dataDir);
            default:
                throw new Error(`Unknown data loader type: ${type}`);
        }
    }
}
exports.DataLoaderFactory = DataLoaderFactory;
//# sourceMappingURL=DataLoaderFactory.js.map