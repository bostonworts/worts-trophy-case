class Season < Struct.new(:start_year, :end_year)
  include Comparable

  STARTING_MONTH = 7
  STARTING_DAY = 1

  def self.current
    for_date(Date.today)
  end

  def self.for_date(date)
    current_year = date.year
    july_1st_in_same_year = date.change(
      month: STARTING_MONTH,
      day: STARTING_DAY,
    )

    if date < july_1st_in_same_year
      new(current_year - 1, current_year)
    else
      new(current_year, current_year + 1)
    end
  end

  def self.from_param(param)
    start_year, end_year = param.split("-").map(&:to_i)
    new(start_year, end_year)
  end

  def <=>(other)
    [start_year, end_year] <=> [other.start_year, other.end_year]
  end

  def date_range
    calculate_start_date(start_year)...calculate_start_date(end_year)
  end

  def description
    "#{start_year}-#{end_year}"
  end

  def end_date
    date_range.reverse_each.first
  end

  def start_date
    date_range.first
  end

  def to_param
    description
  end

  def previous
    Season.new(start_year - 1, end_year - 1)
  end

  def next
    if current?
      nil
    else
      Season.new(start_year + 1, end_year + 1)
    end
  end

  def current?
    self == self.class.current
  end

  private

  def calculate_start_date(year)
    Date.new(year, STARTING_MONTH, STARTING_DAY)
  end
end
