package rpc

import org.scalatest.flatspec.AnyFlatSpec

class RpcConfigSpec extends AnyFlatSpec {
  // Hand-computed ceil(ps / tCK) values for every tCK(avg) row of Table 11-3:
  // (tRCD, tRP, tRC, tRAS, tRRD, tWR, tRESET, tMOD, tZQINIT, tZQCL, tZQCS, tZQRESET, 200us)
  private val expected: Map[Int, Seq[Long]] = Map(
    1250 -> Seq(11, 11, 39, 28, 6, 12, 4000, 12, 1600, 288, 72, 40, 160000),
    1500 -> Seq(10, 10, 33, 24, 5, 10, 3334, 12, 1334, 240, 60, 34, 133334),
    1667 -> Seq(9, 9, 30, 21, 5, 9, 3000, 12, 1200, 216, 54, 30, 119977),
    2500 -> Seq(6, 6, 20, 14, 3, 6, 2000, 12, 800, 144, 36, 20, 80000),
    4000 -> Seq(4, 4, 13, 9, 2, 4, 1250, 12, 500, 90, 23, 13, 50000)
  )

  "RpcConfig" should "list the five tCK(avg) rows of the single Speed-1600 column" in {
    assert(RpcConfig.operatingPoints.map(o => o.tckPs -> o.cl) ==
      Seq(4000 -> 3, 2500 -> 8, 1667 -> 8, 1500 -> 10, 1250 -> 11))
  }

  it should "convert nanosecond minima with ceil(time_ps / tck_ps)" in {
    for ((tck, exp) <- expected) {
      val d = RpcConfig.derived(tck)
      val got = Seq(d.tRCD, d.tRP, d.tRC, d.tRAS, d.tRRD, d.tWR, d.tRESET, d.tMOD, d.tZQINIT, d.tZQCL, d.tZQCS,
        d.tZQRESET, d.clockStable)
      assert(got == exp, s"tCK=$tck")
    }
  }

  it should "keep cycle minima in cycles" in {
    for (tck <- expected.keys) {
      val d = RpcConfig.derived(tck)
      assert(d.tMRD == 4)
      assert(d.tMOD == 12) // max(12 tCK, 15 ns) is 12 tCK for every tCK >= 1.25 ns
    }
  }

  it should "allow a CL only at or above its tCK(avg) minimum" in {
    assert(RpcConfig.legalCls(1250) == Seq(11))
    assert(RpcConfig.legalCls(1500) == Seq(10, 11))
    assert(RpcConfig.legalCls(1667) == Seq(8, 10, 11))
    assert(RpcConfig.legalCls(2500) == Seq(8, 10, 11))
    assert(RpcConfig.legalCls(4000) == Seq(3, 8, 10, 11))
    assert(!RpcConfig.validTck(1249))
  }

  it should "derive both refresh-completion readings from section 5" in {
    val p = RpcTimingParams.datasheet
    assert(p.refreshOpsPerBankFrom64ms == 5000)
    val d = RpcConfig.derived(1250)
    // 3 tREFI + 4096 x 100 ns + 5 ns = 409.905 us
    assert(d.refreshCycles(1, banks = 1, lp = false, loop = false) == 327924)
    // 3 tREFI + 5000 x 100 ns + 5 ns = 500.305 us
    assert(d.refreshCycles(2, banks = 1, lp = false, loop = false) == 400244)
    // loop mode adds tCSLR (2 ns) and tPXCSL (10 ns)
    assert(d.refreshCycles(1, banks = 1, lp = false, loop = true) == 327934)
    // LP, four banks: reading 2 reproduces the datasheet's 64 ms
    assert(d.refreshCycles(2, banks = 4, lp = true, loop = false) == 51207684)
    assert(d.refreshCycles(1, banks = 4, lp = true, loop = false) == 41950724)
  }
}
