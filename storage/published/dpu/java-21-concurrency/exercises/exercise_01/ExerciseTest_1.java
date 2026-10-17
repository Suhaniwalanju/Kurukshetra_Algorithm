public class FibonacciTest {
    @Test
    public void testFib() {
        assertEquals(55L, FibonacciTask.parallelFib(10));
    }
}