require "rails_helper"

describe Competition do
  describe ".in_season" do
    it "returns competitions in the provided season" do
      season = Season.new(2017, 2018)
      comp_in_season = create(:competition, date: Date.parse("2017-08-05"))
      _comp_before_season = create(:competition, date: Date.parse("2017-01-05"))
      _comp_after_season = create(:competition, date: Date.parse("2018-07-05"))

      expect(Competition.in_season(season)).to eq [comp_in_season]
    end
  end

  describe ".seasons_descending" do
    it "returns the distinct seasons for which there are competitions, descending" do
      create(:competition, date: Date.parse("2016-01-01"))
      create(:competition, date: Date.parse("2016-01-01"))
      create(:competition, date: Date.parse("2018-01-01"))
      create(:competition, date: Date.parse("2017-01-01"))

      expect(Competition.seasons_descending.map(&:description)).to eq(["2017-2018", "2016-2017", "2015-2016"])
    end
  end
end
