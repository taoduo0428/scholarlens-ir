import test from "node:test";
import assert from "node:assert/strict";
import {jaegerMountPath, validTraceIds} from "../src/services/traceViewer.ts";

test("only configured same-origin directory mounts are accepted", () => {
  for (const path of ["", null, "https://ui.site/path", "//ui.site", "/a/../b", "/a%2fb",
    "/a?query", "/a#b", "/a\\b", " /jaeger", "/viewer:123", "/viewer\n"]) {
    assert.equal(jaegerMountPath(path), null);
  }
  assert.equal(jaegerMountPath("/internal/jaeger-1/"), "/internal/jaeger-1");
});

test("task detail contributes only canonical trace IDs, without duplicates", () => {
  const id = "1234567890abcdef".repeat(2);
  assert.deepEqual(validTraceIds([id, null, "0".repeat(32), id, id + "/", id.toUpperCase()]), [id]);
  assert.deepEqual(validTraceIds(null), []);
});
