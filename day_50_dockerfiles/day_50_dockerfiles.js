'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { EventEmitter } = require('node:events');

class DockerfileError extends Error {
    constructor(message, lineNumber = null) {
        super(lineNumber ? `Line ${lineNumber}: ${message}` : message);
        this.name = 'DockerfileError';
    }
}

const SUPPORTED = new Set([
    'FROM',
    'RUN',
    'COPY',
    'CMD',
    'ENTRYPOINT',
    'ENV',
    'WORKDIR',
    'EXPOSE',
    'USER'
]);

function parseDockerfile(source) {
    const instructions = [];
    const physicalLines = source.split(/\r?\n/);

    let logical = '';
    let startLine = 0;

    physicalLines.forEach((raw, index) => {
        const lineNumber = index + 1;
        const line = raw.trim();

        if (!line) return;
        if (line.startsWith('#') && logical.length === 0) return;

        if (logical.length === 0) {
            startLine = lineNumber;
        }

        if (line.endsWith('\\')) {
            logical += `${line.slice(0, -1).trim()} `;
            return;
        }

        logical += line;

        const match = logical.match(/^([A-Za-z]+)(?:\s+(.*))?$/);
        if (!match) {
            throw new DockerfileError('Invalid instruction syntax', startLine);
        }

        const keyword = match[1].toUpperCase();
        const arguments = (match[2] || '').trim();

        if (!SUPPORTED.has(keyword)) {
            throw new DockerfileError(
                `Unsupported instruction ${keyword}`,
                startLine
            );
        }

        if (!arguments) {
            throw new DockerfileError(
                `${keyword} requires arguments`,
                startLine
            );
        }

        instructions.push({
            keyword,
            arguments,
            lineNumber: startLine
        });

        logical = '';
        startLine = 0;
    });

    if (logical.length > 0) {
        throw new DockerfileError('Incomplete line continuation', startLine);
    }

    validateDockerfile(instructions);
    return instructions;
}

function validateDockerfile(instructions) {
    if (instructions.length === 0) {
        throw new DockerfileError('Dockerfile is empty');
    }

    if (instructions[0].keyword !== 'FROM') {
        throw new DockerfileError('FROM must be the first effective instruction');
    }

    const fromCount = instructions.filter(
        item => item.keyword === 'FROM'
    ).length;

    if (fromCount !== 1) {
        throw new DockerfileError(
            'This example requires exactly one FROM instruction'
        );
    }

    const envInstructions = instructions.filter(
        item => item.keyword === 'ENV'
    );

    for (const item of envInstructions) {
        if (!item.arguments.includes('=') &&
            item.arguments.split(/\s+/).length < 2) {
            throw new DockerfileError(
                'ENV must use KEY=VALUE or KEY VALUE syntax',
                item.lineNumber
            );
        }

        if (/password|secret|token/i.test(item.arguments)) {
            throw new DockerfileError(
                'Secrets must not be embedded in ENV',
                item.lineNumber
            );
        }
    }

    const copyInstructions = instructions.filter(
        item => item.keyword === 'COPY'
    );

    for (const item of copyInstructions) {
        if (item.arguments.includes('../')) {
            throw new DockerfileError(
                'COPY must not escape the build context',
                item.lineNumber
            );
        }
    }
}

class BuildPolicy extends EventEmitter {
    constructor() {
        super();
        this.results = [];
    }

    evaluate(instructions) {
        const emitResult = (rule, passed, message) => {
            const result = { rule, passed, message };
            this.results.push(result);
            this.emit('rule', result);
        };

        const has = keyword =>
            instructions.some(item => item.keyword === keyword);

        emitResult(
            'base-image',
            has('FROM'),
            'A base image must be declared.'
        );

        emitResult(
            'startup',
            has('CMD') || has('ENTRYPOINT'),
            'The image should define container startup behavior.'
        );

        emitResult(
            'environment-secrets',
            !instructions.some(
                item =>
                    item.keyword === 'ENV' &&
                    /password|secret|token/i.test(item.arguments)
            ),
            'Dockerfile ENV must not contain credentials.'
        );

        emitResult(
            'copy-context',
            !instructions.some(
                item =>
                    item.keyword === 'COPY' &&
                    item.arguments.includes('../')
            ),
            'COPY sources must remain inside the build context.'
        );

        return this.results.every(result => result.passed);
    }
}

class DockerBuildSimulator {
    constructor(instructions) {
        this.instructions = instructions;
        this.layers = [];
        this.environment = new Map();
        this.files = new Map();
    }

    async execute() {
        for (const instruction of this.instructions) {
            await new Promise(resolve => setImmediate(resolve));

            switch (instruction.keyword) {
                case 'FROM':
                    this.layers.push(`base:${instruction.arguments}`);
                    break;

                case 'RUN':
                    this.layers.push(`run:${instruction.arguments}`);
                    break;

                case 'COPY':
                    this.files.set(
                        instruction.arguments,
                        'build-context-content'
                    );
                    this.layers.push(`copy:${instruction.arguments}`);
                    break;

                case 'ENV':
                    this.parseEnvironment(instruction.arguments);
                    this.layers.push('environment');
                    break;

                case 'CMD':
                    this.layers.push(`cmd:${instruction.arguments}`);
                    break;

                case 'ENTRYPOINT':
                    this.layers.push(`entrypoint:${instruction.arguments}`);
                    break;

                default:
                    this.layers.push(
                        `${instruction.keyword.toLowerCase()}:${instruction.arguments}`
                    );
            }
        }

        return {
            layerCount: this.layers.length,
            environment: Object.fromEntries(this.environment),
            files: [...this.files.keys()]
        };
    }

    parseEnvironment(argumentsText) {
        const matches = argumentsText.match(
            /([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|'[^']*'|\S+)/g
        ) || [];

        for (const pair of matches) {
            const separator = pair.indexOf('=');
            const key = pair.slice(0, separator);
            let value = pair.slice(separator + 1);

            if (
                (value.startsWith('"') && value.endsWith('"')) ||
                (value.startsWith("'") && value.endsWith("'"))
            ) {
                value = value.slice(1, -1);
            }

            this.environment.set(key, value);
        }
    }
}

async function main() {
    const dockerfile = `
FROM node:22-bookworm-slim

ENV NODE_ENV=production PORT=8080

WORKDIR /app

COPY package.json .
RUN npm ci --omit=dev

COPY server.js .

ENTRYPOINT ["node", "server.js"]
CMD ["--port", "8080"]
`.trim();

    try {
        const instructions = parseDockerfile(dockerfile);

        console.log('Parsed Dockerfile');
        console.log('-----------------');

        for (const item of instructions) {
            console.log(
                `${item.lineNumber}: ${item.keyword.padEnd(11)} ${item.arguments}`
            );
        }

        const policy = new BuildPolicy();

        policy.on('rule', result => {
            console.log(
                `[${result.passed ? 'PASS' : 'FAIL'}] ${result.rule}: ${result.message}`
            );
        });

        const allowed = policy.evaluate(instructions);

        if (!allowed) {
            throw new DockerfileError('Build policy rejected the Dockerfile');
        }

        const simulator = new DockerBuildSimulator(instructions);
        const result = await simulator.execute();

        console.log('\nSimulated image state');
        console.log('---------------------');
        console.log(`Layers: ${result.layerCount}`);
        console.log(`Environment: ${JSON.stringify(result.environment)}`);
        console.log(`Copied paths: ${result.files.join(', ')}`);

        console.log('\nInstruction roles');
        console.log('-----------------');
        console.log('FROM establishes the base image.');
        console.log('RUN executes build-time commands.');
        console.log('COPY transfers files from the build context.');
        console.log('ENV stores image/container environment configuration.');
        console.log('ENTRYPOINT establishes the primary executable.');
        console.log('CMD supplies default runtime arguments or a default command.');

        console.log('\nRuntime behavior');
        console.log('----------------');
        console.log(
            'ENTRYPOINT plus CMD provides a stable executable with replaceable default arguments.'
        );
        console.log(
            'Changing files referenced by COPY can invalidate subsequent cached build layers.'
        );
        console.log(
            'Secrets should be supplied through an appropriate runtime or build-secret mechanism, not committed to ENV or RUN.'
        );
    } catch (error) {
        if (error instanceof DockerfileError) {
            console.error(`Dockerfile error: ${error.message}`);
            process.exitCode = 1;
        } else {
            console.error(error);
            process.exitCode = 2;
        }
    }
}

main();
