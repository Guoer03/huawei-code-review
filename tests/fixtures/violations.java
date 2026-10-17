public class Bad {
	void check(int x) {
		if (x > 0) return;
		switch (x) {
		case 1:
			break;
		}
	}
}

