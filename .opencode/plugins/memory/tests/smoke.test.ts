import { test } from "node:test";
import assert from "node:assert/strict";
import { isSupportedVersion, isGitCommit } from "../index";

test("isSupportedVersion gates on minimum opencode version", () => {
  assert.equal(isSupportedVersion("1.18.0"), true);
  assert.equal(isSupportedVersion("1.17.10"), true);
  assert.equal(isSupportedVersion("1.17.9"), false);
  assert.equal(isSupportedVersion("0.9.0"), false);
});

test("isGitCommit detects git commit commands only", () => {
  assert.equal(isGitCommit("git commit -m 'x'"), true);
  assert.equal(isGitCommit("git commit"), true);
  assert.equal(isGitCommit("git status"), false);
  assert.equal(isGitCommit("git committer"), false);
});
