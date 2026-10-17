function bad(items: any[]) {
  var result: any = 0;
  for (const index in items) {
    result += items[index];
  }
  return eval(String(result));
}

